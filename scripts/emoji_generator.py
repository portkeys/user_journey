#!/usr/bin/env python3
"""
Smart Avatar Emoji Generator

Generates avatar emojis based on:
1. User's primary activities/interests (from event data)
2. User's location
3. Optional randomness for variety

Usage:
    from emoji_generator import suggest_avatar_emoji

    emoji = suggest_avatar_emoji(
        summary=analysis_summary,      # From EventAnalyzer
        location="Colorado",           # User's location
        strategy="activity_first"      # or "location_first", "random_blend"
    )
"""

import random
from typing import Optional

# Activity-based emoji mappings (primary sport/interest -> emoji)
# Note: Order matters - put more specific patterns before generic ones
ACTIVITY_EMOJI_MAP = {
    # Cycling variants (including race/event names)
    ('cycling', 'biking', 'mtb', 'mountain biking', 'gravel', 'road cycling', 'bikepacking',
     'tour-de-france', 'giro', 'vuelta', 'criterium', 'velonews', 'peloton', 'emtb',
     'british-cycling', 'bike', 'cyclist', 'bicycle'): '🚴',
    ('e-bike', 'ebike', 'electric bike'): '🚲',

    # Running variants
    ('running', 'trail running', 'marathon', 'ultrarunning', 'ultra', 'jogging',
     'trailrunner', 'runner', '5k', '10k', 'half-marathon'): '🏃',

    # Winter sports
    ('skiing', 'backcountry', 'alpine', 'ski touring', 'downhill skiing', 'ski',
     'powder', 'resort'): '⛷️',
    ('snowboarding', 'snowboard'): '🏂',
    ('cross-country skiing', 'nordic skiing', 'xc skiing'): '🎿',

    # Climbing
    ('climbing', 'bouldering', 'rock climbing', 'sport climbing', 'trad climbing',
     'climber'): '🧗',
    ('mountaineering', 'alpinism'): '🏔️',

    # Hiking/Backpacking
    ('hiking', 'backpacking', 'thru-hiking', 'trekking', 'hiker'): '🥾',

    # Water sports
    ('swimming', 'open water', 'lap swimming', 'swimmer'): '🏊',
    ('surfing', 'surf', 'surfer'): '🏄',
    ('kayaking', 'canoeing', 'paddling', 'sup', 'stand up paddle', 'paddler'): '🛶',
    ('fishing', 'fly fishing', 'angling', 'fisherman'): '🎣',

    # Triathlon
    ('triathlon', 'tri', 'ironman', 'triathlete'): '🏊',

    # Wellness
    ('yoga', 'meditation', 'wellness', 'mindfulness', 'yoga journal'): '🧘',

    # Camping/Outdoor living
    ('camping', 'overlanding', 'van life', 'car camping', 'camper'): '🏕️',

    # Adventure/Nature
    ('adventure', 'expedition', 'national-parks', 'public-lands'): '🧭',
}

# Location-based emoji mappings
LOCATION_EMOJI_MAP = {
    # US States/Regions
    'colorado': '🏔️',
    'california': '🌴',
    'seattle': '🌧️',
    'washington': '🌧️',
    'oregon': '🌲',
    'new york': '🗽',
    'nyc': '🗽',
    'texas': '🤠',
    'florida': '🌴',
    'hawaii': '🌺',
    'alaska': '🐻',
    'utah': '🏜️',
    'arizona': '🌵',
    'nevada': '🎰',
    'montana': '🦌',
    'wyoming': '🦬',
    'idaho': '🥔',
    'new mexico': '🌶️',
    'north carolina': '🌲',
    'south carolina': '🌴',
    'vermont': '🍁',
    'maine': '🦞',
    'connecticut': '🍂',
    'massachusetts': '🦞',
    'berkeley': '🌉',
    'san francisco': '🌉',

    # Countries
    'canada': '🍁',
    'mexico': '🌮',
    'france': '🗼',
    'switzerland': '🏔️',
    'japan': '🗾',
    'australia': '🦘',
    'new zealand': '🥝',
    'uk': '🇬🇧',
    'germany': '🍺',
    'italy': '🍕',
    'spain': '🇪🇸',
    'norway': '🇳🇴',
    'iceland': '🧊',
}

# Default outdoor emojis for fallback with variety
DEFAULT_OUTDOOR_EMOJIS = ['🏔️', '🌲', '🌄', '⛰️', '🌿', '🏞️', '🧭', '🌅']


def _get_activity_emoji(tags: dict) -> Optional[str]:
    """
    Find the best activity emoji based on user's top tags.

    Args:
        tags: Dict of tag -> count from user analysis

    Returns:
        Emoji string or None if no match found
    """
    if not tags:
        return None

    # Get top 15 tags by count
    sorted_tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)[:15]
    top_tag_names = [tag.lower() for tag, _ in sorted_tags]

    # Check each activity category
    for keywords, emoji in ACTIVITY_EMOJI_MAP.items():
        for tag in top_tag_names:
            if tag in keywords or any(kw in tag for kw in keywords):
                return emoji

    return None


def _get_location_emoji(location: str) -> Optional[str]:
    """
    Get emoji based on user's location.

    Args:
        location: Location string (city, state, or country)

    Returns:
        Emoji string or None if no match found
    """
    if not location:
        return None

    location_lower = location.lower().strip()

    # Direct match
    if location_lower in LOCATION_EMOJI_MAP:
        return LOCATION_EMOJI_MAP[location_lower]

    # Partial match
    for loc_key, emoji in LOCATION_EMOJI_MAP.items():
        if loc_key in location_lower or location_lower in loc_key:
            return emoji

    return None


def suggest_avatar_emoji(
    summary: Optional[dict] = None,
    location: Optional[str] = None,
    strategy: str = "activity_first",
    seed: Optional[int] = None
) -> str:
    """
    Suggest an avatar emoji for a user based on their data.

    Args:
        summary: Analysis summary dict containing 'tags' key
        location: User's location string
        strategy: One of:
            - "activity_first": Prefer activity-based emoji, fall back to location
            - "location_first": Prefer location-based emoji, fall back to activity
            - "random_blend": Randomly choose between activity and location
            - "activity_only": Only use activity, fall back to default
            - "location_only": Only use location, fall back to default
        seed: Random seed for reproducibility (useful for consistent results)

    Returns:
        Emoji string
    """
    if seed is not None:
        random.seed(seed)

    tags = summary.get('tags', {}) if summary else {}

    activity_emoji = _get_activity_emoji(tags)
    location_emoji = _get_location_emoji(location)

    if strategy == "activity_first":
        return activity_emoji or location_emoji or random.choice(DEFAULT_OUTDOOR_EMOJIS)

    elif strategy == "location_first":
        return location_emoji or activity_emoji or random.choice(DEFAULT_OUTDOOR_EMOJIS)

    elif strategy == "random_blend":
        candidates = [e for e in [activity_emoji, location_emoji] if e]
        if candidates:
            return random.choice(candidates)
        return random.choice(DEFAULT_OUTDOOR_EMOJIS)

    elif strategy == "activity_only":
        return activity_emoji or random.choice(DEFAULT_OUTDOOR_EMOJIS)

    elif strategy == "location_only":
        return location_emoji or random.choice(DEFAULT_OUTDOOR_EMOJIS)

    else:
        # Default to activity_first
        return activity_emoji or location_emoji or random.choice(DEFAULT_OUTDOOR_EMOJIS)


def get_emoji_reason(
    summary: Optional[dict] = None,
    location: Optional[str] = None
) -> dict:
    """
    Get emoji suggestion with explanation of why it was chosen.

    Args:
        summary: Analysis summary dict
        location: User's location string

    Returns:
        Dict with 'emoji', 'reason', and 'source' keys
    """
    tags = summary.get('tags', {}) if summary else {}

    activity_emoji = _get_activity_emoji(tags)
    location_emoji = _get_location_emoji(location)

    if activity_emoji:
        # Find which tag matched
        sorted_tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)[:15]
        top_tag_names = [tag.lower() for tag, _ in sorted_tags]

        matched_activity = None
        for keywords, emoji in ACTIVITY_EMOJI_MAP.items():
            if emoji == activity_emoji:
                for tag in top_tag_names:
                    if tag in keywords or any(kw in tag for kw in keywords):
                        matched_activity = tag
                        break
                if matched_activity:
                    break

        return {
            'emoji': activity_emoji,
            'reason': f"Based on top activity: {matched_activity}",
            'source': 'activity',
            'alternatives': {
                'location': location_emoji,
                'activity': activity_emoji
            }
        }

    elif location_emoji:
        return {
            'emoji': location_emoji,
            'reason': f"Based on location: {location}",
            'source': 'location',
            'alternatives': {
                'location': location_emoji,
                'activity': None
            }
        }

    else:
        default = random.choice(DEFAULT_OUTDOOR_EMOJIS)
        return {
            'emoji': default,
            'reason': "Default outdoor emoji (no activity or location match)",
            'source': 'default',
            'alternatives': {
                'location': None,
                'activity': None
            }
        }


# CLI for testing
if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Test emoji generation")
    parser.add_argument("--location", help="User location")
    parser.add_argument("--summary-file", help="Path to summary JSON file")
    parser.add_argument("--strategy", default="activity_first",
                       choices=["activity_first", "location_first", "random_blend",
                               "activity_only", "location_only"])

    args = parser.parse_args()

    summary = None
    if args.summary_file:
        with open(args.summary_file) as f:
            data = json.load(f)
            summary = data.get('summary', data)

    result = get_emoji_reason(summary=summary, location=args.location)

    print(f"\nEmoji: {result['emoji']}")
    print(f"Reason: {result['reason']}")
    print(f"Source: {result['source']}")
    if result['alternatives']['location'] or result['alternatives']['activity']:
        print(f"Alternatives: location={result['alternatives']['location']}, activity={result['alternatives']['activity']}")
