"""
Generate HTML Report for Robin's User Journey
Beautiful visualizations + LLM-powered narrative insights
Enhanced version with dynamic visualizations
"""

import os
import json
import time
import re
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
import boto3

load_dotenv()


def load_data():
    """Load events and summary data"""
    with open('robin_complete_events.json', 'r') as f:
        events = json.load(f)
    with open('robin_summary.json', 'r') as f:
        summary = json.load(f)
    return events, summary


def get_recent_events(events, days=7):
    """Get events from the last N days"""
    import pandas as pd
    from datetime import timedelta

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
        return []

    dated_events.sort(key=lambda x: x[0], reverse=True)
    latest = dated_events[0][0]
    cutoff = latest - timedelta(days=days)

    recent = [e for dt, e in dated_events if dt > cutoff]
    return recent


def prepare_llm_context(events, summary, recent_events):
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

    recent_sample = []
    for e in recent_events[:30]:
        recent_sample.append({
            'timestamp': e.get('TIMESTAMP'),
            'domain': e.get('DOMAIN'),
            'title': e.get('TITLE'),
            'tags': e.get('TAGS'),
        })

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
        'recent_events': recent_sample,
        'recent_event_count': len(recent_events),
    }

    return context


def call_haiku(context):
    """Call Claude Haiku 4.5 via Bedrock for narrative analysis"""
    print("Calling Haiku 4.5 for narrative analysis...")

    client = boto3.client(
        'bedrock-runtime',
        region_name=os.getenv('AWS_REGION', 'us-east-1'),
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    )

    prompt = """You are a user insights analyst creating a personalized report for "Robin", a power user of Outside Online's media properties.

Based on the data below, generate a warm, engaging narrative report with these sections:

1. **Welcome Message** (2-3 sentences) - A personalized greeting acknowledging Robin as a valued member
2. **Robin's 2025 Outside Memory** (3-4 paragraphs) - Tell the story of Robin's engagement journey over the past year. What themes emerged? How did interests evolve month by month? This is like a "year in review" memory book.
3. **Your Passions** (bullet points with brief explanations) - Identify 5-6 core passions/interests with evidence from the data
4. **Reading Habits** (2-3 paragraphs) - When does Robin read? What patterns emerge? Favorite authors?

IMPORTANT:
- Write in second person ("You", "Your") addressing Robin directly
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

    print(f"  Haiku completed in {elapsed:.1f}s ({result['usage']['output_tokens']} tokens)")

    return narrative


def call_haiku_recent_activity(context):
    """Call Haiku for recent activity spotlight"""
    print("Calling Haiku 4.5 for recent activity spotlight...")

    client = boto3.client(
        'bedrock-runtime',
        region_name=os.getenv('AWS_REGION', 'us-east-1'),
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    )

    prompt = """Based on the recent events data (last 7 days), write a brief, engaging "Recent Activity Spotlight" section for Robin.

Include:
1. A catchy headline summarizing recent interests
2. 2-3 sentences describing what Robin has been exploring lately
3. 3-4 specific article titles or topics they've been reading

Keep it concise, warm, and specific. Use second person ("You"). No markdown headers needed - just flowing text with the headline at the start.

Recent Activity Data:
"""

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 500,
        "temperature": 0.7,
        "messages": [
            {"role": "user", "content": prompt + json.dumps(context.get('recent_events', []), indent=2, default=str)}
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

    print(f"  Recent activity completed in {elapsed:.1f}s")

    return spotlight


def call_gpt5_nano(context):
    """Call GPT-5-nano for structured interest analysis"""
    print("Calling GPT-5-nano for structured interest analysis...")

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
    print(f"  GPT-5-nano completed in {elapsed:.1f}s ({response.usage.completion_tokens} tokens)")

    # Parse JSON response
    try:
        result = result.strip()
        if result.startswith('```'):
            result = re.sub(r'^```json?\n?', '', result)
            result = re.sub(r'\n?```$', '', result)
        analysis = json.loads(result)
        return analysis
    except json.JSONDecodeError as e:
        print(f"  Warning: Could not parse analysis JSON: {e}")
        return {
            "seasonal_patterns": [],
            "emerging_interests": [],
            "core_interests": [],
            "casual_interests": []
        }


def call_gpt5_nano_dynamic_charts(context):
    """Call GPT-5-nano to generate interest evolution chart"""
    print("Calling GPT-5-nano for evolution chart generation...")

    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

    # Prepare monthly tag data for visualization
    monthly_data = context.get('temporal_patterns', {}).get('by_month', {})
    tags = context.get('top_tags', {})

    prompt = """You are a data visualization expert. Create a Chart.js LINE CHART showing how the user's TOP 5 interests evolved over time (monthly).

REQUIREMENTS:
- Type: 'line' chart
- X-axis: months (use the monthly data keys as labels)
- Y-axis: relative interest level (0-100 scale)
- Show 5 different colored lines for the top 5 interests
- Use smooth curves (tension: 0.4)
- Make it visually appealing

Use this exact JSON format:
{
  "title": "Your Interests Over Time",
  "description": "How your top interests evolved month by month",
  "config": {
    "type": "line",
    "data": { "labels": [...], "datasets": [...] },
    "options": { ... }
  }
}

Colors to use for the 5 lines: '#FFD100', '#000000', '#555555', '#888888', '#BBBBBB'

Monthly activity data:
""" + json.dumps(monthly_data, indent=2) + """

Top interest tags (with counts):
""" + json.dumps(dict(list(tags.items())[:10]), indent=2) + """

Return ONLY a single JSON object (not an array). No markdown, no explanation, just the JSON object."""

    start = time.time()
    response = client.chat.completions.create(
        model="gpt-5-nano",
        messages=[
            {"role": "system", "content": "You are a data visualization expert. Return only valid JSON."},
            {"role": "user", "content": prompt}
        ],
    )
    elapsed = time.time() - start

    result = response.choices[0].message.content
    print(f"  Dynamic charts completed in {elapsed:.1f}s")

    # Parse the JSON response
    try:
        # Clean up potential markdown formatting
        result = result.strip()
        if result.startswith('```'):
            result = re.sub(r'^```json?\n?', '', result)
            result = re.sub(r'\n?```$', '', result)

        chart = json.loads(result)
        return chart
    except json.JSONDecodeError as e:
        print(f"  Warning: Could not parse chart JSON: {e}")
        return None


def generate_html_report(summary, haiku_narrative, gpt_analysis, recent_spotlight, recent_events):
    """Generate beautiful HTML report with visualizations"""

    # Prepare chart data
    publications = summary.get('publications', {})
    pub_labels = list(publications.keys())[:10]
    pub_values = [publications[k] for k in pub_labels]

    tags = summary.get('tags', {})
    tag_labels = list(tags.keys())[:15]
    tag_values = [tags[k] for k in tag_labels]

    temporal = summary.get('temporal', {})
    hours_utc = temporal.get('by_hour', {})

    # Convert UTC hours to Mountain Time (UTC-7 for MST, UTC-6 for MDT)
    # Using UTC-7 as default (Mountain Standard Time)
    MT_OFFSET = -7
    hours_mt = {}
    for h_utc, count in hours_utc.items():
        h_mt = (int(h_utc) + MT_OFFSET) % 24
        hours_mt[h_mt] = hours_mt.get(h_mt, 0) + count

    hour_labels = [f"{h}:00" for h in range(24)]
    hour_values = [hours_mt.get(h, 0) for h in range(24)]

    # Calculate peak hour in Mountain Time
    peak_hours = sorted([(h, c) for h, c in hours_mt.items()], key=lambda x: -x[1])[:3]
    peak_hour_mt = peak_hours[0][0] if peak_hours else 12
    timezone_note = f"Peak activity: {peak_hour_mt}:00 MT"

    days = temporal.get('by_day_of_week', {})
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    day_values = [days.get(d, 0) for d in day_order]

    months = temporal.get('by_month', {})
    month_labels = sorted(months.keys())
    month_values = [months[m] for m in month_labels]

    engagement = summary.get('engagement_metrics', {})

    # Prepare recent content for spotlight - separate articles from videos
    import html as html_lib
    from datetime import datetime as dt_parser

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
        # For videos, also exclude generic "| Outside TV" suffixes
        if is_video and '| outside tv' in title_lower:
            # But keep if there's substantial content before it
            main_title = title_lower.split('|')[0].strip()
            if len(main_title) < 10:
                return False
        # Skip location-only titles
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
        # Remove "| Outside TV" suffix for cleaner display
        if is_video and '|' in title:
            title = title.split('|')[0].strip()
        return html_lib.escape(title[:55])

    # Separate into reads and watches
    recent_reads = []
    recent_watches = []

    for e in recent_events:
        if is_video_event(e):
            if is_valid_content(e, is_video=True):
                recent_watches.append(e)
        else:
            if is_valid_content(e, is_video=False):
                recent_reads.append(e)

    # Build Latest Reads HTML
    recent_reads_html = ""
    for e in recent_reads[:4]:
        title = clean_title(e.get('TITLE', ''), is_video=False)
        url = e.get('URL') or e.get('PAGE_URL') or '#'
        date_str = format_date(e.get('TIMESTAMP'))
        recent_reads_html += f'''<div class="recent-article">
            <a href="{html_lib.escape(url)}" target="_blank" class="article-link">{title}</a>
            <span class="article-date">{date_str}</span>
        </div>'''

    if not recent_reads_html:
        recent_reads_html = '<div class="recent-article"><span class="article-title" style="opacity: 0.7;">No recent articles</span></div>'

    # Build Latest Watch HTML
    recent_watch_html = ""
    for e in recent_watches[:4]:
        title = clean_title(e.get('TITLE', ''), is_video=True)
        url = e.get('URL') or e.get('PAGE_URL') or '#'
        date_str = format_date(e.get('TIMESTAMP'))
        recent_watch_html += f'''<div class="recent-article">
            <a href="{html_lib.escape(url)}" target="_blank" class="article-link">{title}</a>
            <span class="article-date">{date_str}</span>
        </div>'''

    if not recent_watch_html:
        recent_watch_html = '<div class="recent-article"><span class="article-title" style="opacity: 0.7;">No recent videos</span></div>'

    # Convert markdown to basic HTML
    def md_to_html(text):
        # Headers
        text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
        # Bold
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        # Italic
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        # Bullet points
        text = re.sub(r'^- (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
        text = re.sub(r'(<li>.*</li>\n?)+', r'<ul>\g<0></ul>', text)
        # Paragraphs
        text = re.sub(r'\n\n', '</p><p>', text)
        text = f'<p>{text}</p>'
        text = re.sub(r'<p>\s*<h', '<h', text)
        text = re.sub(r'</h(\d)>\s*</p>', r'</h\1>', text)
        text = re.sub(r'<p>\s*<ul>', '<ul>', text)
        text = re.sub(r'</ul>\s*</p>', '</ul>', text)
        return text

    haiku_html = md_to_html(haiku_narrative)

    # Build structured analysis components from gpt_analysis dict
    # Seasonal Patterns Cards
    seasonal_html = ""
    for sp in gpt_analysis.get('seasonal_patterns', []):
        emoji = sp.get('emoji', '🌿')
        season = sp.get('season', 'Season')
        activities = ', '.join(sp.get('activities', []))
        insight = sp.get('insight', '')
        seasonal_html += f'''
        <div class="season-card">
            <div class="season-header">{emoji} {season}</div>
            <div class="season-activities">{activities}</div>
            <div class="season-insight">{insight}</div>
        </div>'''

    # Emerging Interests
    emerging_html = ""
    for ei in gpt_analysis.get('emerging_interests', []):
        topic = ei.get('topic', '')
        evidence = ei.get('evidence', '')
        emerging_html += f'''
        <div class="emerging-item">
            <span class="emerging-topic">🚀 {topic}</span>
            <span class="emerging-evidence">{evidence}</span>
        </div>'''

    # Core Interests
    core_html = ""
    for ci in gpt_analysis.get('core_interests', []):
        topic = ci.get('topic', '')
        strength = ci.get('strength', '')
        evidence = ci.get('evidence', '')
        core_html += f'''
        <div class="interest-card core">
            <div class="interest-topic">{topic}</div>
            <div class="interest-strength">{strength}</div>
            <div class="interest-evidence">{evidence}</div>
        </div>'''

    # Casual Interests
    casual_html = ""
    for ci in gpt_analysis.get('casual_interests', []):
        topic = ci.get('topic', '')
        note = ci.get('note', '')
        casual_html += f'''
        <div class="interest-card casual">
            <div class="interest-topic">{topic}</div>
            <div class="interest-note">{note}</div>
        </div>'''

    # Build ecosystem stats from summary
    ecosystem = summary.get('ecosystem', {})
    tf = ecosystem.get('trailforks', {})
    editorial = ecosystem.get('editorial', {})
    ecosystem_html = f'''
    <div class="ecosystem-grid" style="grid-template-columns: repeat(5, 1fr);">
        <div class="ecosystem-card editorial">
            <div class="eco-icon">📰</div>
            <div class="eco-title">Editorial</div>
            <div class="eco-stats">
                <div class="eco-stat"><span class="eco-number">{editorial.get('articles', 0):,}</span> articles read</div>
                <div class="eco-stat"><span class="eco-number">{editorial.get('events', 0):,}</span> page views</div>
            </div>
        </div>
        <div class="ecosystem-card trailforks">
            <div class="eco-icon">🚵</div>
            <div class="eco-title">Trailforks</div>
            <div class="eco-stats">
                <div class="eco-stat"><span class="eco-number">{tf.get('unique_rides', 0)}</span> rides tracked</div>
                <div class="eco-stat"><span class="eco-number">{tf.get('app', 0) + tf.get('web', 0):,}</span> interactions</div>
            </div>
        </div>
        <div class="ecosystem-card gaia">
            <div class="eco-icon">🗺️</div>
            <div class="eco-title">Gaia GPS</div>
            <div class="eco-stats">
                <div class="eco-stat"><span class="eco-number">{ecosystem.get('gaia_gps', {}).get('events', 0)}</span> sessions</div>
            </div>
        </div>
        <div class="ecosystem-card watch">
            <div class="eco-icon">🎬</div>
            <div class="eco-title">Outside Watch</div>
            <div class="eco-stats">
                <div class="eco-stat"><span class="eco-number">{ecosystem.get('outside_watch', {}).get('events', 0)}</span> videos</div>
            </div>
        </div>
        <div class="ecosystem-card app">
            <div class="eco-icon">📱</div>
            <div class="eco-title">Outside App</div>
            <div class="eco-stats">
                <div class="eco-stat"><span class="eco-number">{ecosystem.get('outside_app', {}).get('events', 0)}</span> sessions</div>
            </div>
        </div>
    </div>'''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Robin's 2025 Outside Memory</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --primary: #FFD100;
            --primary-dark: #E6BC00;
            --secondary: #000000;
            --accent: #333333;
            --bg: #F7F7F7;
            --card-bg: #FFFFFF;
            --text: #000000;
            --text-light: #555555;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }}

        .hero {{
            background: var(--secondary);
            color: white;
            padding: 60px 20px;
            text-align: center;
        }}

        .hero h1 {{
            color: var(--primary);
            font-size: 2.5rem;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        }}

        .hero p {{
            font-size: 1.2rem;
            opacity: 0.9;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}

        .stat-card {{
            background: var(--card-bg);
            border-radius: 12px;
            padding: 25px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            transition: transform 0.2s;
        }}

        .stat-card:hover {{
            transform: translateY(-5px);
        }}

        .stat-number {{
            font-size: 2.5rem;
            font-weight: bold;
            color: var(--secondary);
            text-shadow: 1px 1px 0 var(--primary);
        }}

        .stat-label {{
            color: var(--text-light);
            font-size: 0.9rem;
            margin-top: 5px;
        }}

        /* Recent Activity Spotlight - Featured Section */
        .spotlight-section {{
            background: linear-gradient(135deg, var(--secondary) 0%, #1a1a1a 100%);
            border-radius: 16px;
            padding: 40px;
            margin: 30px 0;
            color: white;
        }}

        .spotlight-section h2 {{
            color: var(--primary);
            margin-bottom: 20px;
            font-size: 1.8rem;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}

        .spotlight-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            align-items: start;
        }}

        .spotlight-narrative {{
            font-size: 1.1rem;
            line-height: 1.8;
            color: #e0e0e0;
        }}

        .spotlight-narrative strong {{
            color: var(--primary);
            text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
        }}

        .recent-articles-list {{
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 20px;
            border-left: 4px solid var(--primary);
        }}

        .recent-articles-list h3 {{
            color: var(--primary);
            margin-bottom: 15px;
            font-size: 1rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        .recent-article {{
            padding: 12px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 12px;
        }}

        .recent-article:last-child {{
            border-bottom: none;
        }}

        .article-link {{
            font-size: 0.9rem;
            color: white;
            text-decoration: none;
            line-height: 1.4;
            flex: 1;
            transition: color 0.2s;
        }}

        .article-link:hover {{
            color: var(--primary);
            text-decoration: underline;
        }}

        .article-date {{
            font-size: 0.75rem;
            color: rgba(255,255,255,0.5);
            white-space: nowrap;
            padding-top: 2px;
        }}

        .article-domain {{
            font-size: 0.75rem;
            color: var(--primary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .article-title {{
            font-size: 0.95rem;
            color: white;
        }}

        .content-lists-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 25px;
        }}

        /* Ecosystem Cards */
        .ecosystem-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin: 20px 0;
        }}

        .ecosystem-card {{
            background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            color: white;
            transition: transform 0.2s;
        }}

        .ecosystem-card:hover {{
            transform: translateY(-3px);
        }}

        .ecosystem-card.editorial {{ border-top: 3px solid var(--primary); }}
        .ecosystem-card.trailforks {{ border-top: 3px solid #4CAF50; }}
        .ecosystem-card.gaia {{ border-top: 3px solid #2196F3; }}
        .ecosystem-card.watch {{ border-top: 3px solid #FF5722; }}
        .ecosystem-card.app {{ border-top: 3px solid #9C27B0; }}

        .eco-icon {{ font-size: 2rem; margin-bottom: 8px; }}
        .eco-title {{ font-weight: bold; margin-bottom: 10px; color: var(--primary); }}
        .eco-stat {{ font-size: 0.85rem; color: #bbb; margin: 4px 0; }}
        .eco-number {{ color: white; font-weight: bold; font-size: 1.1rem; }}

        /* Seasonal Pattern Cards */
        .seasonal-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}

        .season-card {{
            background: var(--card-bg);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            border-left: 4px solid var(--primary);
        }}

        .season-header {{
            font-size: 1.2rem;
            font-weight: bold;
            color: var(--secondary);
            margin-bottom: 10px;
        }}

        .season-activities {{
            font-size: 0.9rem;
            color: var(--accent);
            margin-bottom: 8px;
            font-weight: 500;
        }}

        .season-insight {{
            font-size: 0.85rem;
            color: var(--text-light);
            font-style: italic;
        }}

        /* Interest Cards */
        .interests-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }}

        .interest-card {{
            background: var(--card-bg);
            border-radius: 10px;
            padding: 15px 20px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.06);
        }}

        .interest-card.core {{
            border-left: 4px solid var(--primary);
            background: linear-gradient(135deg, #fffbea 0%, #fff 100%);
        }}

        .interest-card.casual {{
            border-left: 4px solid #888;
        }}

        .interest-topic {{
            font-weight: bold;
            color: var(--secondary);
            font-size: 1rem;
            margin-bottom: 5px;
        }}

        .interest-strength {{
            font-size: 0.8rem;
            color: #666;
            background: var(--primary);
            display: inline-block;
            padding: 2px 8px;
            border-radius: 10px;
            margin-bottom: 5px;
        }}

        .interest-evidence, .interest-note {{
            font-size: 0.85rem;
            color: var(--text-light);
        }}

        /* Emerging Interests */
        .emerging-list {{
            margin: 15px 0;
        }}

        .emerging-item {{
            display: flex;
            align-items: flex-start;
            gap: 10px;
            padding: 10px 0;
            border-bottom: 1px solid #eee;
        }}

        .emerging-topic {{
            font-weight: bold;
            color: var(--secondary);
            white-space: nowrap;
        }}

        .emerging-evidence {{
            font-size: 0.9rem;
            color: var(--text-light);
        }}

        /* Evolution Chart */
        .evolution-chart-container {{
            background: #fafafa;
            border-radius: 12px;
            padding: 20px;
            margin-top: 20px;
        }}

        .evolution-chart-container h4 {{
            color: var(--secondary);
            margin-bottom: 5px;
        }}

        .section {{
            background: var(--card-bg);
            border-radius: 16px;
            padding: 30px;
            margin: 30px 0;
            box-shadow: 0 2px 15px rgba(0,0,0,0.06);
        }}

        .section h2 {{
            color: var(--secondary);
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid var(--primary);
            display: inline-block;
        }}

        .chart-container {{
            position: relative;
            height: 300px;
            margin: 20px 0;
        }}

        .chart-row {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 30px;
        }}

        .chart-subtitle {{
            color: var(--text-light);
            margin-bottom: 10px;
            font-size: 0.9rem;
        }}

        .narrative {{
            font-size: 1.05rem;
            line-height: 1.8;
        }}

        .narrative h2 {{
            color: var(--secondary);
            margin: 25px 0 15px 0;
            font-size: 1.5rem;
        }}

        .narrative h3 {{
            color: var(--accent);
            margin: 20px 0 10px 0;
        }}

        .narrative ul {{
            margin: 15px 0 15px 25px;
        }}

        .narrative li {{
            margin: 8px 0;
        }}

        .narrative strong {{
            color: var(--secondary);
            background: linear-gradient(to bottom, transparent 60%, var(--primary) 60%);
            padding: 0 2px;
        }}

        .analysis-box {{
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            border-left: 4px solid var(--secondary);
            padding: 20px 25px;
            margin: 20px 0;
            border-radius: 0 12px 12px 0;
        }}

        /* Dynamic Charts Section */
        .dynamic-charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 25px;
            margin-top: 20px;
        }}

        .dynamic-chart-card {{
            background: #fafafa;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #e0e0e0;
        }}

        .dynamic-chart-card h4 {{
            color: var(--secondary);
            margin-bottom: 8px;
            font-size: 1.1rem;
        }}

        .chart-description {{
            color: var(--text-light);
            font-size: 0.85rem;
            margin-bottom: 15px;
        }}

        .tag-cloud {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin: 20px 0;
        }}

        .tag {{
            background: var(--primary);
            color: var(--secondary);
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
        }}

        .tag.large {{
            font-size: 1rem;
            padding: 8px 18px;
            background: var(--secondary);
            color: var(--primary);
        }}

        .tag.medium {{
            background: var(--accent);
            color: white;
        }}

        .tag.small {{
            background: #666666;
            color: white;
            font-size: 0.8rem;
        }}

        footer {{
            text-align: center;
            padding: 40px;
            background: var(--secondary);
            color: white;
            margin-top: 40px;
        }}

        footer a {{
            color: var(--primary);
        }}

        @media (max-width: 768px) {{
            .hero h1 {{
                font-size: 1.8rem;
            }}
            .chart-row, .spotlight-grid, .dynamic-charts-grid, .content-lists-grid, .ecosystem-grid, .seasonal-grid, .interests-grid {{
                grid-template-columns: 1fr;
            }}
            .stats-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
            .ecosystem-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}
    </style>
</head>
<body>
    <div class="hero">
        <h1>🏔️ Robin's 2025 Outside Memory</h1>
        <p>Your personalized journey through adventure, cycling, and outdoor exploration</p>
        <p style="margin-top: 15px; opacity: 0.8;">
            {temporal.get('first_event', '')[:10]} → {temporal.get('last_event', '')[:10]}
        </p>
    </div>

    <div class="container">
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-number">{engagement.get('total_events', 0):,}</div>
                <div class="stat-label">Pages Explored</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{engagement.get('total_days_tracked', 0)}</div>
                <div class="stat-label">Days of Adventure</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{engagement.get('unique_articles', 0):,}</div>
                <div class="stat-label">Unique Articles</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{engagement.get('unique_authors_read', 0)}</div>
                <div class="stat-label">Authors Discovered</div>
            </div>
        </div>

        <!-- ECOSYSTEM - Top Featured Section -->
        <div class="section" style="background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%); color: white;">
            <h2 style="color: var(--primary); border-bottom-color: var(--primary);">🌍 Your Outside Ecosystem</h2>
            <p class="chart-subtitle" style="color: #aaa;">Your activity across the Outside family of apps and platforms</p>
            {ecosystem_html}
        </div>

        <!-- RECENT ACTIVITY SPOTLIGHT - Featured Section -->
        <div class="spotlight-section">
            <h2>🔥 Recent Activity Spotlight</h2>
            <div class="spotlight-grid">
                <div class="spotlight-narrative">
                    {recent_spotlight}
                </div>
                <div class="content-lists-grid">
                    <div class="recent-articles-list">
                        <h3>📖 Latest Reads</h3>
                        {recent_reads_html}
                    </div>
                    <div class="recent-articles-list">
                        <h3>🎬 Latest Watch</h3>
                        {recent_watch_html}
                    </div>
                </div>
            </div>
            <!-- Seasonal Patterns inline -->
            <div style="margin-top: 30px;">
                <h3 style="color: var(--primary); margin-bottom: 15px;">📅 Seasonal Patterns</h3>
                <div class="seasonal-grid">
                    {seasonal_html if seasonal_html else '<p style="color: #aaa;">Seasonal data being analyzed...</p>'}
                </div>
            </div>
        </div>

        <div class="section">
            <h2>📊 Your Reading Journey</h2>
            <div class="chart-row">
                <div>
                    <p class="chart-subtitle">Monthly Activity</p>
                    <div class="chart-container">
                        <canvas id="monthlyChart"></canvas>
                    </div>
                </div>
                <div>
                    <p class="chart-subtitle">Publications</p>
                    <div class="chart-container">
                        <canvas id="pubChart"></canvas>
                    </div>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>⏰ When You Read</h2>
            <p class="chart-subtitle">Converted to Mountain Time (MT) based on Colorado location. {timezone_note}</p>
            <div class="chart-row">
                <div>
                    <p class="chart-subtitle">Hour of Day (Mountain Time)</p>
                    <div class="chart-container">
                        <canvas id="hourChart"></canvas>
                    </div>
                </div>
                <div>
                    <p class="chart-subtitle">Day of Week</p>
                    <div class="chart-container">
                        <canvas id="dayChart"></canvas>
                    </div>
                </div>
            </div>
        </div>

        <div class="section">
            <h2>🏷️ Your Interests</h2>

            <!-- Core vs Casual Interests - First -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-bottom: 30px;">
                <div>
                    <h3 style="color: var(--secondary); margin-bottom: 15px;">⭐ Core Interests</h3>
                    <p class="chart-subtitle">Your deep, consistent passions</p>
                    <div class="interests-grid" style="grid-template-columns: 1fr;">
                        {core_html if core_html else '<p style="color: var(--text-light);">Analyzing...</p>'}
                    </div>
                </div>
                <div>
                    <h3 style="color: var(--secondary); margin-bottom: 15px;">🌱 Casual Interests</h3>
                    <p class="chart-subtitle">Topics you explore occasionally</p>
                    <div class="interests-grid" style="grid-template-columns: 1fr;">
                        {casual_html if casual_html else '<p style="color: var(--text-light);">Analyzing...</p>'}
                    </div>
                </div>
            </div>

            {f'''<h3 style="margin-top: 20px; color: var(--secondary);">🚀 Emerging Interests</h3>
            <div class="emerging-list">{emerging_html}</div>''' if emerging_html else ''}

            <h3 style="margin-top: 30px; color: var(--secondary);">📊 Interest Distribution</h3>
            <div class="tag-cloud">
                {"".join([f'<span class="tag large">{t}</span>' for t in tag_labels[:5]])}
                {"".join([f'<span class="tag medium">{t}</span>' for t in tag_labels[5:10]])}
                {"".join([f'<span class="tag small">{t}</span>' for t in tag_labels[10:15]])}
            </div>
            <div class="chart-container" style="height: 350px;">
                <canvas id="tagsChart"></canvas>
            </div>
        </div>

        <div class="section narrative">
            <h2>📖 Your Story</h2>
            {haiku_html}
        </div>
    </div>

    <footer>
        <p>Generated with ❤️ by Outside Online Analytics</p>
        <p style="margin-top: 10px; opacity: 0.7;">
            Report created: {datetime.now().strftime('%B %d, %Y at %H:%M')}
        </p>
    </footer>

    <script>
        // Outside Online brand colors
        const colors = {{
            primary: '#FFD100',
            secondary: '#000000',
            accent: '#333333',
            chartColors: [
                '#FFD100', '#000000', '#333333', '#666666',
                '#999999', '#CCCCCC', '#E6BC00', '#B8960A'
            ]
        }};

        // Monthly Activity Chart
        new Chart(document.getElementById('monthlyChart'), {{
            type: 'line',
            data: {{
                labels: {json.dumps(month_labels)},
                datasets: [{{
                    label: 'Page Views',
                    data: {json.dumps(month_values)},
                    borderColor: colors.primary,
                    backgroundColor: 'rgba(255, 209, 0, 0.15)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 5,
                    pointHoverRadius: 7,
                    pointBackgroundColor: colors.secondary,
                    pointBorderColor: colors.primary,
                    pointBorderWidth: 2,
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    y: {{ beginAtZero: true, grid: {{ color: 'rgba(0,0,0,0.08)' }} }},
                    x: {{ grid: {{ display: false }} }}
                }}
            }}
        }});

        // Publications Chart
        new Chart(document.getElementById('pubChart'), {{
            type: 'doughnut',
            data: {{
                labels: {json.dumps(pub_labels)},
                datasets: [{{
                    data: {json.dumps(pub_values)},
                    backgroundColor: [
                        '#FFD100', '#000000', '#333333', '#666666',
                        '#999999', '#E6BC00', '#B8960A', '#CCCCCC',
                        '#444444', '#777777'
                    ],
                    borderWidth: 2,
                    borderColor: '#FFFFFF',
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ position: 'right', labels: {{ boxWidth: 12, color: '#000000' }} }}
                }}
            }}
        }});

        // Hour of Day Chart
        new Chart(document.getElementById('hourChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(hour_labels)},
                datasets: [{{
                    label: 'Activity',
                    data: {json.dumps(hour_values)},
                    backgroundColor: colors.primary,
                    borderColor: colors.secondary,
                    borderWidth: 1,
                    borderRadius: 4,
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    y: {{ beginAtZero: true, grid: {{ color: 'rgba(0,0,0,0.08)' }} }},
                    x: {{ grid: {{ display: false }}, ticks: {{ maxRotation: 45 }} }}
                }}
            }}
        }});

        // Day of Week Chart
        new Chart(document.getElementById('dayChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(day_order)},
                datasets: [{{
                    label: 'Activity',
                    data: {json.dumps(day_values)},
                    backgroundColor: colors.secondary,
                    borderColor: colors.primary,
                    borderWidth: 2,
                    borderRadius: 4,
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    y: {{ beginAtZero: true, grid: {{ color: 'rgba(0,0,0,0.08)' }} }},
                    x: {{ grid: {{ display: false }} }}
                }}
            }}
        }});

        // Tags Chart
        new Chart(document.getElementById('tagsChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(tag_labels)},
                datasets: [{{
                    label: 'Mentions',
                    data: {json.dumps(tag_values)},
                    backgroundColor: colors.primary,
                    borderColor: colors.secondary,
                    borderWidth: 1,
                    borderRadius: 4,
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                indexAxis: 'y',
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    x: {{ beginAtZero: true, grid: {{ color: 'rgba(0,0,0,0.08)' }} }},
                    y: {{ grid: {{ display: false }} }}
                }}
            }}
        }});

    </script>
</body>
</html>'''

    return html


def main():
    print("=" * 60)
    print("GENERATING ROBIN'S 2025 OUTSIDE MEMORY")
    print("=" * 60)

    # Load data
    print("\nLoading data...")
    events, summary = load_data()
    print(f"  Loaded {len(events):,} events")

    # Get recent events
    recent_events = get_recent_events(events, days=7)
    print(f"  Recent events (7 days): {len(recent_events)}")

    # Prepare LLM context
    context = prepare_llm_context(events, summary, recent_events)

    # Call LLMs
    print("\n" + "-" * 40)
    haiku_narrative = call_haiku(context)

    print()
    recent_spotlight = call_haiku_recent_activity(context)

    print()
    gpt_analysis = call_gpt5_nano(context)

    # Generate HTML report
    print("\n" + "-" * 40)
    print("Generating HTML report...")
    html = generate_html_report(summary, haiku_narrative, gpt_analysis, recent_spotlight, recent_events)

    # Save report
    output_file = 'robin_journey_report.html'
    with open(output_file, 'w') as f:
        f.write(html)

    file_size = os.path.getsize(output_file) / 1024
    print(f"  Saved to {output_file} ({file_size:.1f} KB)")

    print("\n" + "=" * 60)
    print("REPORT COMPLETE!")
    print("=" * 60)
    print(f"\nOpen {output_file} in your browser to view the report.")


if __name__ == "__main__":
    main()
