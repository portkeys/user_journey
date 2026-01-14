"""
Report Data Builder - Generate JSON data for user reports
Combines event analysis with LLM-generated insights
"""

import os
import json
import time
import re
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
import boto3

from event_analyzer import EventAnalyzer, load_events
from emoji_generator import suggest_avatar_emoji, get_emoji_reason

load_dotenv()


def call_haiku(context: dict, user_name: str) -> str:
    """Call Claude Haiku 4.5 via Bedrock for narrative analysis"""
    print(f"  Calling Haiku 4.5 for {user_name}'s narrative...")

    client = boto3.client(
        'bedrock-runtime',
        region_name=os.getenv('AWS_REGION', 'us-east-1'),
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    )

    prompt = f"""You are a user insights analyst creating a personalized report for "{user_name}", a power user of Outside Online's media properties.

Based on the data below, generate a warm, engaging narrative report with these sections:

1. **Welcome Message** (2-3 sentences) - A personalized greeting acknowledging {user_name} as a valued member
2. **{user_name}'s 2025 Outside Memory** (3-4 paragraphs) - Tell the story of their engagement journey over the past year. What themes emerged? How did interests evolve month by month? This is like a "year in review" memory book.
3. **Your Passions** (bullet points with brief explanations) - Identify 5-6 core passions/interests with evidence from the data
4. **Reading Habits** (2-3 paragraphs) - When do they read? What patterns emerge? Favorite authors?

IMPORTANT:
- Write in second person ("You", "Your") addressing {user_name} directly
- Be specific - cite actual article titles, author names, and tags from the data
- Keep it warm and appreciative - this is for the user to see
- Use concrete numbers where relevant
- Format with markdown headers and bullet points
- Do NOT include recommendations or recent activity sections - we handle those separately

User Data:
"""

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "temperature": 0.7,
        "messages": [
            {"role": "user", "content": prompt + json.dumps(context, indent=2, default=str)}
        ]
    })

    start = time.time()
    response = client.invoke_model(
        modelId=os.getenv('BEDROCK_MODEL_ID'),
        body=body,
        contentType='application/json',
        accept='application/json'
    )
    elapsed = time.time() - start

    result = json.loads(response['body'].read())
    narrative = result['content'][0]['text']

    print(f"    Haiku completed in {elapsed:.1f}s ({result['usage']['output_tokens']} tokens)")
    return narrative


def call_haiku_recent_activity(recent_events: list, user_name: str) -> str:
    """Call Haiku for recent activity spotlight"""
    print(f"  Calling Haiku 4.5 for {user_name}'s recent activity spotlight...")

    client = boto3.client(
        'bedrock-runtime',
        region_name=os.getenv('AWS_REGION', 'us-east-1'),
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    )

    prompt = f"""Based on the recent events data (last 7 days), write a brief, engaging "Recent Activity Spotlight" section for {user_name}.

Include:
1. A catchy headline summarizing recent interests
2. 2-3 sentences describing what {user_name} has been exploring lately
3. 3-4 specific article titles or topics they've been reading

Keep it concise, warm, and specific. Use second person ("You"). No markdown headers needed - just flowing text with the headline at the start.

Recent Activity Data:
"""

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 500,
        "temperature": 0.7,
        "messages": [
            {"role": "user", "content": prompt + json.dumps(recent_events[:30], indent=2, default=str)}
        ]
    })

    start = time.time()
    response = client.invoke_model(
        modelId=os.getenv('BEDROCK_MODEL_ID'),
        body=body,
        contentType='application/json',
        accept='application/json'
    )
    elapsed = time.time() - start

    result = json.loads(response['body'].read())
    spotlight = result['content'][0]['text']

    print(f"    Recent activity completed in {elapsed:.1f}s")
    return spotlight


def call_gpt5_nano(context: dict) -> dict:
    """Call GPT-5-nano for structured interest analysis"""
    print("  Calling GPT-5-nano for structured interest analysis...")

    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    prompt = """Analyze this user's interest evolution. Return a JSON object with these exact keys:

{
  "seasonal_patterns": [
    {"season": "Summer", "emoji": "☀️", "activities": ["activity1", "activity2"], "insight": "One sentence about summer behavior"}
  ],
  "emerging_interests": [
    {"topic": "topic name", "evidence": "Brief reason why this is emerging"}
  ],
  "core_interests": [
    {"topic": "topic name", "strength": "description like 'Very Strong' or 'Strong'", "evidence": "Brief supporting fact"}
  ],
  "casual_interests": [
    {"topic": "topic name", "note": "Brief note about occasional engagement"}
  ]
}

REQUIREMENTS:
- seasonal_patterns: 2-4 seasons with emoji, 2-3 activities each, one-sentence insight
- emerging_interests: 2-4 topics that appeared recently or are growing
- core_interests: 3-5 deep, consistent interests with evidence
- casual_interests: 3-5 lighter/occasional interests
- Be specific with actual topic/tag names from the data
- Keep insights SHORT (one sentence max)
- Return ONLY valid JSON, no markdown

Data:
"""

    start = time.time()
    response = client.chat.completions.create(
        model="gpt-5-nano",
        messages=[
            {"role": "system", "content": "You are a data analyst. Return only valid JSON."},
            {"role": "user", "content": prompt + json.dumps(context, indent=2, default=str)}
        ],
    )
    elapsed = time.time() - start

    result = response.choices[0].message.content
    print(f"    GPT-5-nano completed in {elapsed:.1f}s ({response.usage.completion_tokens} tokens)")

    try:
        result = result.strip()
        if result.startswith('```'):
            result = re.sub(r'^```json?\n?', '', result)
            result = re.sub(r'\n?```$', '', result)
        analysis = json.loads(result)
        return analysis
    except json.JSONDecodeError as e:
        print(f"    Warning: Could not parse analysis JSON: {e}")
        return {
            "seasonal_patterns": [],
            "emerging_interests": [],
            "core_interests": [],
            "casual_interests": []
        }


def prepare_llm_context(events: list, summary: dict) -> dict:
    """Prepare context for LLM analysis"""
    sample_events = []
    seen_titles = set()
    for e in events:
        title = e.get('TITLE', '')
        if title and title not in seen_titles and len(sample_events) < 50:
            sample_events.append({
                'timestamp': e.get('TIMESTAMP'),
                'domain': e.get('DOMAIN'),
                'title': title,
                'path': e.get('PATH'),
                'tags': e.get('TAGS'),
            })
            seen_titles.add(title)

    context = {
        'total_events': len(events),
        'date_range': {
            'start': summary.get('temporal', {}).get('first_event'),
            'end': summary.get('temporal', {}).get('last_event'),
            'days': summary.get('temporal', {}).get('total_days'),
        },
        'publications': dict(list(summary.get('publications', {}).items())[:10]),
        'top_tags': dict(list(summary.get('tags', {}).items())[:30]),
        'top_authors': dict(list(summary.get('authors', {}).items())[:15]),
        'content_categories': dict(list(summary.get('content_categories', {}).items())[:15]),
        'temporal_patterns': {
            'by_hour': summary.get('temporal', {}).get('by_hour'),
            'by_day': summary.get('temporal', {}).get('by_day_of_week'),
            'by_month': summary.get('temporal', {}).get('by_month'),
        },
        'engagement': summary.get('engagement_metrics', {}),
        'sample_events': sample_events,
    }

    return context


def extract_recent_activity(events: list, timezone_offset: int = -7) -> dict:
    """Extract recent reads and watches for display"""
    GENERIC_PATTERNS = ['home', 'velo -', 'welcome to', 'backpacker -',
                        'trailrunner -', 'run -', 'climbing -', 'ski -', 'yoga journal -',
                        'outside magazine', '- outside']
    EXACT_MATCHES = ['home', 'outside magazine', 'outside', 'velonews', 'outside tv']

    def is_video_event(event):
        domain = (event.get('DOMAIN') or '').lower()
        return 'watch' in domain or 'tv' in domain

    def is_valid_content(event, is_video=False):
        title = event.get('TITLE')
        if not title:
            return False
        title_lower = title.lower().strip()
        if len(title_lower) < 15:
            return False
        if title_lower in EXACT_MATCHES:
            return False
        for pattern in GENERIC_PATTERNS:
            if pattern in title_lower:
                return False
        if is_video and '| outside tv' in title_lower:
            main_title = title_lower.split('|')[0].strip()
            if len(main_title) < 10:
                return False
        if title_lower.count(',') == 1 and len(title_lower) < 30:
            return False
        return True

    def format_date(timestamp_str):
        try:
            dt = pd.to_datetime(timestamp_str)
            return dt.strftime('%b %d')
        except:
            return ''

    def clean_title(title, is_video=False):
        if is_video and '|' in title:
            title = title.split('|')[0].strip()
        return title[:55]

    # Get recent events (last 7 days)
    dated_events = []
    for e in events:
        ts = e.get('TIMESTAMP')
        if ts:
            try:
                dt = pd.to_datetime(ts)
                dated_events.append((dt, e))
            except:
                pass

    if not dated_events:
        return {'latest_reads': [], 'latest_watches': []}

    dated_events.sort(key=lambda x: x[0], reverse=True)
    latest = dated_events[0][0]
    cutoff = latest - timedelta(days=7)
    recent_events = [e for dt, e in dated_events if dt > cutoff]

    # Separate reads and watches
    latest_reads = []
    latest_watches = []

    for e in recent_events:
        if is_video_event(e):
            if is_valid_content(e, is_video=True) and len(latest_watches) < 4:
                latest_watches.append({
                    'title': clean_title(e.get('TITLE', ''), is_video=True),
                    'url': e.get('URL') or e.get('PAGE_URL') or '#',
                    'date': format_date(e.get('TIMESTAMP'))
                })
        else:
            if is_valid_content(e, is_video=False) and len(latest_reads) < 4:
                latest_reads.append({
                    'title': clean_title(e.get('TITLE', ''), is_video=False),
                    'url': e.get('URL') or e.get('PAGE_URL') or '#',
                    'date': format_date(e.get('TIMESTAMP'))
                })

    return {
        'latest_reads': latest_reads,
        'latest_watches': latest_watches
    }


def build_report_data(user_config: dict, events_file: str, skip_llm: bool = False, auto_emoji: bool = False) -> dict:
    """
    Build complete report data for a user.

    Args:
        user_config: User configuration from registry
        events_file: Path to user's events JSON file
        skip_llm: If True, skip LLM calls (for testing)
        auto_emoji: If True, auto-generate emoji from activity/location instead of using config

    Returns:
        Complete data structure for report rendering
    """
    user_name = user_config.get('display_name', 'User')
    timezone_offset = user_config.get('timezone_offset', -7)

    print(f"\nBuilding report data for {user_name}...")

    # Load and analyze events
    print(f"  Loading events from {events_file}...")
    events = load_events(events_file)
    print(f"  Loaded {len(events):,} events")

    analyzer = EventAnalyzer(events, user_config)
    summary = analyzer.run_full_analysis()
    print(f"  Analysis complete")

    # Get recent events
    recent_events = analyzer.get_recent_events(days=7)
    print(f"  Recent events (7 days): {len(recent_events)}")

    # Extract recent activity for display
    recent_activity = extract_recent_activity(events, timezone_offset)

    # Generate LLM insights
    llm_insights = {}
    if not skip_llm:
        context = prepare_llm_context(events, summary)

        # Haiku narrative
        llm_insights['narrative'] = call_haiku(context, user_name)

        # Recent activity spotlight
        recent_sample = [{'timestamp': e.get('TIMESTAMP'), 'domain': e.get('DOMAIN'),
                         'title': e.get('TITLE'), 'tags': e.get('TAGS')} for e in recent_events[:30]]
        llm_insights['recent_spotlight'] = call_haiku_recent_activity(recent_sample, user_name)

        # GPT-5-nano structured analysis
        gpt_analysis = call_gpt5_nano(context)
        llm_insights['seasonal_patterns'] = gpt_analysis.get('seasonal_patterns', [])
        llm_insights['emerging_interests'] = gpt_analysis.get('emerging_interests', [])
        llm_insights['core_interests'] = gpt_analysis.get('core_interests', [])
        llm_insights['casual_interests'] = gpt_analysis.get('casual_interests', [])
    else:
        print("  Skipping LLM calls (--skip-llm flag)")
        llm_insights = {
            'narrative': 'LLM narrative not generated (skip_llm=True)',
            'recent_spotlight': 'Recent activity spotlight not generated',
            'seasonal_patterns': [],
            'emerging_interests': [],
            'core_interests': [],
            'casual_interests': []
        }

    # Generate smart emoji suggestion based on activity and location
    location = user_config.get('location', '')
    emoji_info = get_emoji_reason(summary=summary, location=location)
    suggested_emoji = emoji_info['emoji']
    emoji_reason = emoji_info['reason']

    # Use suggested emoji if auto_emoji=True, otherwise use config (or suggested as fallback)
    config_emoji = user_config.get('avatar_emoji')
    if auto_emoji:
        final_emoji = suggested_emoji
        print(f"  Auto-emoji: {final_emoji} ({emoji_reason})")
    elif config_emoji:
        final_emoji = config_emoji
    else:
        final_emoji = suggested_emoji
        print(f"  No emoji in config, using suggested: {final_emoji} ({emoji_reason})")

    # Build final output
    output = {
        'user': {
            'display_name': user_config.get('display_name'),
            'slug': user_config.get('slug'),
            'timezone_offset': timezone_offset,
            'timezone_name': user_config.get('timezone_name', 'UTC'),
            'location': user_config.get('location'),
            'avatar_emoji': final_emoji,
            'suggested_emoji': suggested_emoji,
            'emoji_reason': emoji_reason
        },
        'summary': summary,
        'llm_insights': llm_insights,
        'recent_activity': recent_activity,
        'generated_at': datetime.utcnow().isoformat() + 'Z'
    }

    return output


def save_report_data(data: dict, output_path: str):
    """Save report data to JSON file"""
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    file_size = os.path.getsize(output_path) / 1024
    print(f"  Saved to {output_path} ({file_size:.1f} KB)")
