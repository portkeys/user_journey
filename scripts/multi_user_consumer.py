#!/usr/bin/env python3
"""
Multi-User Kafka Consumer
Consumes from power_user_events topic and splits by user_id (message key)

Topic schema:
  - Key: user_id (UUID string)
  - Value: Event JSON with USERNAME field

Output:
  - events/{user_slug}_events.json per user
  - Updates data/users.json with discovered users
"""

import os
import sys
import json
import re
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
from confluent_kafka import Consumer, KafkaError, TopicPartition

load_dotenv()

# Default topic for power users (can override via env or CLI)
DEFAULT_TOPIC = 'power_user_events'


def create_consumer(group_id=None):
    """Create and configure Kafka consumer for Confluent Cloud"""
    config = {
        'bootstrap.servers': os.getenv('KAFKA_BOOTSTRAP_SERVERS'),
        'sasl.mechanisms': 'PLAIN',
        'security.protocol': 'SASL_SSL',
        'sasl.username': os.getenv('KAFKA_API_KEY'),
        'sasl.password': os.getenv('KAFKA_API_SECRET'),
        'group.id': group_id or f'power-users-export-{datetime.now().strftime("%Y%m%d%H%M%S")}',
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': False,
        'fetch.max.bytes': 52428800,  # 50MB
        'max.partition.fetch.bytes': 10485760,  # 10MB per partition
    }
    return Consumer(config)


def get_topic_info(consumer, topic):
    """Get partition and offset information for a topic"""
    metadata = consumer.list_topics(topic, timeout=10)

    if topic not in metadata.topics:
        raise ValueError(f"Topic '{topic}' not found. Available topics: {list(metadata.topics.keys())}")

    partitions = metadata.topics[topic].partitions
    total_messages = 0
    partition_info = []

    for partition_id in partitions.keys():
        tp = TopicPartition(topic, partition_id)
        low, high = consumer.get_watermark_offsets(tp, timeout=10)
        count = high - low
        total_messages += count
        partition_info.append({
            'partition': partition_id,
            'low_offset': low,
            'high_offset': high,
            'message_count': count
        })

    return {
        'topic': topic,
        'partitions': partition_info,
        'total_messages': total_messages
    }


def slugify(name):
    """Convert display name to URL-safe slug"""
    if not name:
        return 'unknown'
    # Lowercase, replace spaces with underscores, remove special chars
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '_', slug)
    slug = re.sub(r'_+', '_', slug).strip('_')
    return slug or 'unknown'


def fetch_multi_user_events(topic=None, output_dir='events', batch_size=1000):
    """
    Fetch events from multi-user topic and split by user_id.

    Args:
        topic: Kafka topic name (defaults to power_user_events)
        output_dir: Directory to save per-user event files
        batch_size: Progress update frequency

    Returns:
        Dict mapping user_id -> {username, slug, event_count, events}
    """
    topic = topic or os.getenv('KAFKA_TOPIC_POWER_USERS', DEFAULT_TOPIC)
    consumer = create_consumer()

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Get topic info
    print(f"Connecting to topic: {topic}")
    try:
        topic_info = get_topic_info(consumer, topic)
    except ValueError as e:
        print(f"ERROR: {e}")
        consumer.close()
        return {}

    total_expected = topic_info['total_messages']
    print(f"Total messages in topic: {total_expected:,}")
    print(f"Partitions: {len(topic_info['partitions'])}")

    # Subscribe and start consuming
    consumer.subscribe([topic])

    # Track events per user: user_id -> {username, events: []}
    users_data = defaultdict(lambda: {'username': None, 'events': []})

    total_events = 0
    empty_polls = 0
    max_empty_polls = 30
    partitions_eof = set()

    start_time = datetime.now()
    print(f"\nStarting multi-user export at {start_time.strftime('%H:%M:%S')}...")
    print("-" * 60)

    try:
        while empty_polls < max_empty_polls:
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                empty_polls += 1
                if empty_polls % 10 == 0:
                    print(f"  Waiting for messages... ({empty_polls}/{max_empty_polls})")
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    partitions_eof.add(msg.partition())
                    if len(partitions_eof) >= len(topic_info['partitions']):
                        print(f"Reached end of all partitions")
                        break
                    continue
                else:
                    print(f"Error: {msg.error()}")
                    continue

            empty_polls = 0

            try:
                # Get user_id from message key
                user_id = msg.key().decode('utf-8') if msg.key() else 'unknown'

                # Parse event value
                event = json.loads(msg.value().decode('utf-8'))

                # Extract username from event (for display name)
                username = event.get('USERNAME') or 'Unknown'

                # Add kafka metadata
                event['_kafka_partition'] = msg.partition()
                event['_kafka_offset'] = msg.offset()
                event['_kafka_timestamp'] = msg.timestamp()[1] if msg.timestamp()[0] else None
                event['_user_id'] = user_id  # Store user_id in event for reference

                # Store event under user
                users_data[user_id]['username'] = username
                users_data[user_id]['events'].append(event)

                total_events += 1

                # Progress update
                if total_events % batch_size == 0:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    rate = total_events / elapsed if elapsed > 0 else 0
                    pct = (total_events / total_expected * 100) if total_expected > 0 else 0
                    print(f"  Fetched {total_events:,} events ({pct:.1f}%) - {len(users_data)} users - {rate:.0f}/sec")

            except json.JSONDecodeError as e:
                print(f"Failed to parse message at offset {msg.offset()}: {e}")
            except Exception as e:
                print(f"Error processing message: {e}")

    finally:
        consumer.close()

    elapsed = (datetime.now() - start_time).total_seconds()
    print("-" * 60)
    print(f"Export complete!")
    print(f"  Total events: {total_events:,}")
    print(f"  Total users: {len(users_data)}")
    print(f"  Time elapsed: {elapsed:.1f} seconds")

    # Process and save per-user files
    print(f"\nSaving per-user event files to {output_dir}/...")

    user_summary = []
    for user_id, data in users_data.items():
        username = data['username']
        events = data['events']
        slug = slugify(username)

        # Handle duplicate slugs by appending user_id suffix
        output_file = os.path.join(output_dir, f'{slug}_events.json')

        # Save events
        with open(output_file, 'w') as f:
            json.dump(events, f, default=str)

        file_size = os.path.getsize(output_file) / 1024  # KB

        user_summary.append({
            'user_id': user_id,
            'username': username,
            'slug': slug,
            'event_count': len(events),
            'file': output_file,
            'file_size_kb': round(file_size, 1)
        })

        print(f"  {username} ({slug}): {len(events):,} events -> {output_file} ({file_size:.1f} KB)")

    return user_summary


def update_user_registry(user_summary, registry_path='data/users.json'):
    """
    Update the user registry with discovered users.
    Preserves existing user data, adds new users.
    """
    # Load existing registry
    if os.path.exists(registry_path):
        with open(registry_path, 'r') as f:
            registry = json.load(f)
    else:
        registry = {'users': []}

    existing_ids = {u['user_id'] for u in registry['users']}
    existing_slugs = {u['slug'] for u in registry['users']}

    # Default timezone/location placeholders
    TIMEZONE_PRESETS = [
        {'offset': -8, 'name': 'Pacific Time', 'location': 'California'},
        {'offset': -7, 'name': 'Mountain Time', 'location': 'Colorado'},
        {'offset': -6, 'name': 'Central Time', 'location': 'Texas'},
        {'offset': -5, 'name': 'Eastern Time', 'location': 'New York'},
    ]

    EMOJIS = ['🏔️', '🌊', '🏜️', '🌲', '🚴', '🏃', '⛷️', '🧗']

    added = 0
    for i, user in enumerate(user_summary):
        if user['user_id'] in existing_ids:
            continue

        # Ensure unique slug
        slug = user['slug']
        if slug in existing_slugs:
            slug = f"{slug}_{user['user_id'][:4]}"

        # Assign placeholder timezone (rotate through presets)
        tz = TIMEZONE_PRESETS[i % len(TIMEZONE_PRESETS)]
        emoji = EMOJIS[i % len(EMOJIS)]

        new_user = {
            'user_id': user['user_id'],
            'display_name': user['username'],
            'slug': slug,
            'timezone_offset': tz['offset'],
            'timezone_name': tz['name'],
            'location': tz['location'],
            'avatar_emoji': emoji,
            'events_file': user['file']
        }

        registry['users'].append(new_user)
        existing_ids.add(user['user_id'])
        existing_slugs.add(slug)
        added += 1

    # Save updated registry
    with open(registry_path, 'w') as f:
        json.dump(registry, f, indent=2)

    print(f"\nUpdated {registry_path}: {added} new users added, {len(registry['users'])} total")
    return registry


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Consume multi-user events from Kafka')
    parser.add_argument('--topic', '-t', type=str, default=DEFAULT_TOPIC,
                        help=f'Kafka topic name (default: {DEFAULT_TOPIC})')
    parser.add_argument('--output-dir', '-o', type=str, default='events',
                        help='Output directory for per-user event files (default: events/)')
    parser.add_argument('--info', action='store_true',
                        help='Just show topic info without consuming')
    parser.add_argument('--no-registry-update', action='store_true',
                        help='Skip updating data/users.json')
    args = parser.parse_args()

    print("=" * 60)
    print("MULTI-USER KAFKA CONSUMER")
    print("=" * 60)

    if args.info:
        # Just show topic info
        consumer = create_consumer()
        try:
            info = get_topic_info(consumer, args.topic)
            print(json.dumps(info, indent=2))
        except ValueError as e:
            print(f"ERROR: {e}")
        finally:
            consumer.close()
        return

    # Full export
    user_summary = fetch_multi_user_events(
        topic=args.topic,
        output_dir=args.output_dir
    )

    if user_summary and not args.no_registry_update:
        update_user_registry(user_summary)

    print("\n" + "=" * 60)
    print("EXPORT COMPLETE")
    print("=" * 60)
    print(f"\nNext steps:")
    print(f"  1. Review data/users.json and update timezone/location for each user")
    print(f"  2. Generate reports: python scripts/batch_generate.py")
    print(f"  3. Or for specific user: python scripts/batch_generate.py --user <slug>")


if __name__ == "__main__":
    main()
