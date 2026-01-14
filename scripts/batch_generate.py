#!/usr/bin/env python3
"""
Batch Generate Reports - CLI tool to generate user journey reports
Usage:
    python batch_generate.py                    # Generate for all users with events
    python batch_generate.py --user robin       # Generate for specific user
    python batch_generate.py --user robin --skip-llm  # Skip LLM calls (testing)
"""

import argparse
import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.report_data_builder import build_report_data, save_report_data


def load_user_registry(registry_path: str = 'data/users.json') -> list:
    """Load user registry from JSON file"""
    with open(registry_path, 'r') as f:
        data = json.load(f)
    return data.get('users', [])


def find_events_file(user_config: dict, base_dir: str = '.') -> str:
    """Find the events file for a user"""
    # Check explicit events_file in config
    if user_config.get('events_file'):
        path = os.path.join(base_dir, user_config['events_file'])
        if os.path.exists(path):
            return path

    # Check events directory
    slug = user_config.get('slug', 'unknown')
    events_dir_path = os.path.join(base_dir, 'events', f'{slug}_events.json')
    if os.path.exists(events_dir_path):
        return events_dir_path

    # Check root directory with various naming patterns
    patterns = [
        f'{slug}_complete_events.json',
        f'{slug}_events.json',
        f'{slug}.json',
    ]
    for pattern in patterns:
        path = os.path.join(base_dir, pattern)
        if os.path.exists(path):
            return path

    return None


def generate_for_user(user_config: dict, base_dir: str = '.', skip_llm: bool = False) -> bool:
    """Generate report data for a single user"""
    user_name = user_config.get('display_name', 'Unknown')
    slug = user_config.get('slug', 'unknown')

    print(f"\n{'='*60}")
    print(f"Processing: {user_name} ({slug})")
    print('='*60)

    # Find events file
    events_file = find_events_file(user_config, base_dir)
    if not events_file:
        print(f"  ERROR: No events file found for {user_name}")
        print(f"  Expected locations:")
        print(f"    - {base_dir}/events/{slug}_events.json")
        print(f"    - {base_dir}/{slug}_complete_events.json")
        if user_config.get('events_file'):
            print(f"    - {base_dir}/{user_config['events_file']}")
        return False

    # Build report data
    try:
        data = build_report_data(user_config, events_file, skip_llm=skip_llm)
    except Exception as e:
        print(f"  ERROR: Failed to build report data: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Save to data directory
    output_path = os.path.join(base_dir, 'data', f'{slug}.json')
    save_report_data(data, output_path)

    print(f"  SUCCESS: Report data generated for {user_name}")
    return True


def main():
    parser = argparse.ArgumentParser(description='Generate user journey report data')
    parser.add_argument('--user', '-u', type=str, help='Generate for specific user (by slug)')
    parser.add_argument('--skip-llm', action='store_true', help='Skip LLM calls (for testing)')
    parser.add_argument('--registry', type=str, default='data/users.json', help='Path to user registry')
    parser.add_argument('--all', '-a', action='store_true', help='Generate for all users (even without events)')
    args = parser.parse_args()

    # Determine base directory (script is in scripts/, so go up one level)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(script_dir)
    os.chdir(base_dir)

    print("="*60)
    print("USER JOURNEY REPORT GENERATOR")
    print("="*60)
    print(f"Working directory: {os.getcwd()}")

    # Load user registry
    registry_path = args.registry
    if not os.path.exists(registry_path):
        print(f"ERROR: User registry not found at {registry_path}")
        sys.exit(1)

    users = load_user_registry(registry_path)
    print(f"Loaded {len(users)} users from registry")

    # Filter to specific user if requested
    if args.user:
        users = [u for u in users if u.get('slug') == args.user]
        if not users:
            print(f"ERROR: User '{args.user}' not found in registry")
            sys.exit(1)

    # Process users
    success_count = 0
    skip_count = 0
    error_count = 0

    for user_config in users:
        # Check if user has events file
        events_file = find_events_file(user_config, base_dir)
        if not events_file and not args.all:
            print(f"\nSkipping {user_config.get('display_name')} - no events file found")
            skip_count += 1
            continue

        if generate_for_user(user_config, base_dir, skip_llm=args.skip_llm):
            success_count += 1
        else:
            error_count += 1

    # Summary
    print("\n" + "="*60)
    print("GENERATION COMPLETE")
    print("="*60)
    print(f"  Successful: {success_count}")
    print(f"  Skipped:    {skip_count}")
    print(f"  Errors:     {error_count}")

    if success_count > 0:
        print(f"\nReport data files are in: {os.path.join(base_dir, 'data')}/")
        print("View reports at: report.html?user=<slug>")


if __name__ == "__main__":
    main()
