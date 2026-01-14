"""
Kafka Consumer for Power User Events
Fetches events from Confluent Cloud for analysis
Optimized for bulk export of 21K+ messages
"""

import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv
from confluent_kafka import Consumer, KafkaError, TopicPartition

load_dotenv()


def create_consumer(group_id=None):
    """Create and configure Kafka consumer for Confluent Cloud"""
    config = {
        'bootstrap.servers': os.getenv('KAFKA_BOOTSTRAP_SERVERS'),
        'sasl.mechanisms': 'PLAIN',
        'security.protocol': 'SASL_SSL',
        'sasl.username': os.getenv('KAFKA_API_KEY'),
        'sasl.password': os.getenv('KAFKA_API_SECRET'),
        'group.id': group_id or f'robin-export-{datetime.now().strftime("%Y%m%d%H%M%S")}',
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': False,  # Manual control for bulk reads
        'fetch.max.bytes': 52428800,  # 50MB - larger batches
        'max.partition.fetch.bytes': 10485760,  # 10MB per partition
    }
    return Consumer(config)


def get_topic_info(consumer, topic):
    """Get partition and offset information for a topic"""
    metadata = consumer.list_topics(topic, timeout=10)
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


def fetch_all_events(output_file='robin_complete_events.json', batch_size=1000):
    """Fetch ALL events from Kafka topic efficiently

    Args:
        output_file: Path to save the complete events
        batch_size: Number of messages to process before progress update

    Returns:
        List of all event dictionaries
    """
    consumer = create_consumer()
    topic = os.getenv('KAFKA_TOPIC')

    # Get topic info first
    print(f"Connecting to topic: {topic}")
    topic_info = get_topic_info(consumer, topic)
    total_expected = topic_info['total_messages']
    print(f"Total messages in topic: {total_expected:,}")
    print(f"Partitions: {len(topic_info['partitions'])}")

    # Subscribe and start consuming
    consumer.subscribe([topic])

    events = []
    empty_polls = 0
    max_empty_polls = 30  # More patience for large datasets
    partitions_eof = set()

    start_time = datetime.now()
    print(f"\nStarting bulk export at {start_time.strftime('%H:%M:%S')}...")
    print("-" * 50)

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

            empty_polls = 0  # Reset on successful message

            try:
                event = json.loads(msg.value().decode('utf-8'))
                # Add metadata
                event['_kafka_partition'] = msg.partition()
                event['_kafka_offset'] = msg.offset()
                event['_kafka_timestamp'] = msg.timestamp()[1] if msg.timestamp()[0] else None
                events.append(event)

                # Progress update
                if len(events) % batch_size == 0:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    rate = len(events) / elapsed if elapsed > 0 else 0
                    pct = (len(events) / total_expected * 100) if total_expected > 0 else 0
                    print(f"  Fetched {len(events):,} events ({pct:.1f}%) - {rate:.0f} events/sec")

            except json.JSONDecodeError as e:
                print(f"Failed to parse message at offset {msg.offset()}: {e}")

    finally:
        consumer.close()

    elapsed = (datetime.now() - start_time).total_seconds()
    print("-" * 50)
    print(f"Export complete!")
    print(f"  Total events: {len(events):,}")
    print(f"  Time elapsed: {elapsed:.1f} seconds")
    print(f"  Average rate: {len(events)/elapsed:.0f} events/sec")

    # Save to file
    print(f"\nSaving to {output_file}...")
    with open(output_file, 'w') as f:
        json.dump(events, f, default=str)

    file_size = os.path.getsize(output_file) / (1024 * 1024)
    print(f"Saved {file_size:.1f} MB to {output_file}")

    return events


def explore_schema(events, sample_size=5):
    """Analyze event schema and types"""
    if not events:
        print("No events to analyze")
        return None

    print("\n" + "=" * 60)
    print("EVENT SCHEMA EXPLORATION")
    print("=" * 60)

    # Collect all unique keys across all events
    all_keys = set()
    event_types = {}

    for event in events:
        # Exclude kafka metadata keys
        keys = {k for k in event.keys() if not k.startswith('_kafka')}
        all_keys.update(keys)

        # Try to identify event type
        event_type = (event.get('type') or event.get('event_type') or
                      event.get('eventType') or event.get('action') or 'unknown')
        event_types[event_type] = event_types.get(event_type, 0) + 1

    print(f"\nTotal events: {len(events):,}")
    print(f"\nUnique fields ({len(all_keys)}): {sorted(all_keys)}")

    print(f"\nEvent types distribution:")
    for etype, count in sorted(event_types.items(), key=lambda x: -x[1])[:20]:
        pct = count / len(events) * 100
        print(f"  {etype}: {count:,} ({pct:.1f}%)")

    if len(event_types) > 20:
        print(f"  ... and {len(event_types) - 20} more types")

    print(f"\nSample events:")
    for i, event in enumerate(events[:sample_size]):
        print(f"\n--- Event {i+1} ---")
        # Pretty print without kafka metadata
        clean_event = {k: v for k, v in event.items() if not k.startswith('_kafka')}
        print(json.dumps(clean_event, indent=2, default=str)[:1500])

    return {
        'total_events': len(events),
        'fields': sorted(all_keys),
        'event_types': event_types,
    }


if __name__ == "__main__":
    # Check for command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == '--info':
        # Just show topic info
        consumer = create_consumer()
        topic = os.getenv('KAFKA_TOPIC')
        info = get_topic_info(consumer, topic)
        print(json.dumps(info, indent=2))
        consumer.close()
    else:
        # Full export
        output_file = sys.argv[1] if len(sys.argv) > 1 else 'robin_complete_events.json'
        events = fetch_all_events(output_file=output_file)

        if events:
            schema_info = explore_schema(events)
