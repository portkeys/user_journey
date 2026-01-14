"""
Build User Profile from Event Analysis
Transforms raw event analysis into the UserInsights schema
"""

import json
from datetime import datetime, timedelta
from typing import Optional


def calculate_interest_strength(count: int, total_events: int, recency_days: int) -> tuple[str, float]:
    """Calculate interest strength and score"""
    # Score based on engagement frequency
    frequency_score = min(count / total_events * 10, 1.0)

    # Recency factor (decay over time)
    recency_factor = max(0, 1 - (recency_days / 365))

    score = (frequency_score * 0.7) + (recency_factor * 0.3)

    # Determine strength category
    if score >= 0.7:
        strength = "core"
    elif score >= 0.4:
        strength = "active"
    elif score >= 0.2:
        strength = "casual"
    elif recency_days > 90:
        strength = "dormant"
    else:
        strength = "emerging"

    return strength, round(score, 3)


def calculate_engagement_level(total_events: int, days: int) -> str:
    """Determine user engagement level"""
    events_per_day = total_events / max(days, 1)

    if events_per_day >= 30:
        return "power_user"
    elif events_per_day >= 10:
        return "regular"
    elif events_per_day >= 3:
        return "casual"
    elif events_per_day >= 0.5:
        return "churning"
    else:
        return "new"


def estimate_timezone(peak_hours_utc: list[int]) -> str:
    """Estimate timezone based on peak activity hours"""
    # If peak is 12-18 UTC, likely US time zones
    avg_peak = sum(peak_hours_utc) / len(peak_hours_utc) if peak_hours_utc else 12

    if 12 <= avg_peak <= 18:
        return "America/Denver"  # Mountain Time
    elif 17 <= avg_peak <= 23:
        return "America/New_York"  # Eastern Time
    elif 20 <= avg_peak or avg_peak <= 4:
        return "America/Los_Angeles"  # Pacific Time
    else:
        return "UTC"


def build_user_insights(summary: dict, events: list, user_id: str) -> dict:
    """Build complete UserInsights object from analysis"""

    now = datetime.utcnow()
    temporal = summary.get('temporal', {})
    total_events = summary.get('engagement_metrics', {}).get('total_events', len(events))
    total_days = temporal.get('total_days', 365)

    # === CORE INTERESTS ===
    tags = summary.get('tags', {})
    core_interests = []
    for topic, count in list(tags.items())[:20]:
        strength, score = calculate_interest_strength(count, total_events, 30)
        core_interests.append({
            "topic": topic,
            "strength": strength,
            "score": score,
            "engagement_count": count,
            "trend": "stable"  # Would need time-series analysis to determine
        })

    # === TEMPORAL PATTERNS ===
    hours_data = temporal.get('by_hour', {})
    # Convert string keys to int, sort by count
    hours_sorted = sorted(
        [(int(h), c) for h, c in hours_data.items()],
        key=lambda x: -x[1]
    )
    peak_hours = [h for h, c in hours_sorted[:3]]

    days_data = temporal.get('by_day_of_week', {})
    days_sorted = sorted(days_data.items(), key=lambda x: -x[1])
    peak_days = [d for d, c in days_sorted[:3]]

    # === COHORT TAGS ===
    cohort_tags = []
    publications = summary.get('publications', {})

    # Determine sport focus
    if publications.get('VeloNews', 0) > total_events * 0.1:
        cohort_tags.append("cyclist")
    if publications.get('Run', 0) + publications.get('TrailRunner', 0) > total_events * 0.05:
        cohort_tags.append("runner")
    if publications.get('Trailforks', 0) > total_events * 0.05:
        cohort_tags.append("mountain-biker")
    if summary.get('email_traffic_count', 0) > total_events * 0.01:
        cohort_tags.append("newsletter-engaged")

    # Content style
    article_eng = summary.get('article_engagement', {})
    content_types = article_eng.get('content_types', {})
    if content_types.get('reviews', 0) > 100:
        cohort_tags.append("gear-enthusiast")
    if content_types.get('how_to', 0) > 10:
        cohort_tags.append("skill-builder")

    # Engagement level tag
    engagement_level = calculate_engagement_level(total_events, total_days)
    if engagement_level == "power_user":
        cohort_tags.append("power-user")

    # === AUTHORS ===
    authors = summary.get('authors', {})
    favorite_authors = [
        {
            "author_name": name,
            "articles_read": count,
            "affinity_score": round(min(count / 20, 1.0), 2)
        }
        for name, count in list(authors.items())[:10]
    ]

    # === RECENT ACTIVITY ===
    recent_events = []
    import pandas as pd
    for e in events:
        ts = e.get('TIMESTAMP')
        if ts:
            try:
                dt = pd.to_datetime(ts)
                if dt > now - timedelta(days=7):
                    recent_events.append(e)
            except:
                pass

    recent_topics = {}
    for e in recent_events:
        tags_raw = e.get('TAGS')
        if tags_raw and isinstance(tags_raw, str) and tags_raw.startswith('['):
            try:
                tag_list = [t.strip() for t in tags_raw[1:-1].split(',') if t.strip()]
                for tag in tag_list:
                    recent_topics[tag.lower()] = recent_topics.get(tag.lower(), 0) + 1
            except:
                pass

    emerging_topics = [
        {"topic": t, "strength": "emerging", "score": round(c / len(recent_events), 2) if recent_events else 0}
        for t, c in sorted(recent_topics.items(), key=lambda x: -x[1])[:5]
    ]

    # === BUILD FINAL OBJECT ===
    user_insights = {
        "user_id": user_id,
        "generated_at": now.isoformat() + "Z",
        "schema_version": "1.0.0",

        "long_term_profile": {
            "user_id": user_id,
            "last_updated": now.isoformat() + "Z",

            "core_interests": core_interests,
            "interest_embedding": None,  # Would be computed by embedding model

            "preferred_publications": list(publications.keys())[:5],
            "content_preferences": [
                {"format": "reviews", "preference_score": 0.7, "avg_engagement_depth": 0.6},
                {"format": "news", "preference_score": 0.5, "avg_engagement_depth": 0.4},
                {"format": "long-reads", "preference_score": 0.4, "avg_engagement_depth": 0.8},
            ],
            "favorite_authors": favorite_authors,

            "engagement_level": engagement_level,
            "lifetime_events": total_events,
            "account_age_days": total_days,
            "avg_monthly_events": round(total_events / max(total_days / 30, 1), 1),

            "temporal_pattern": {
                "peak_hours_utc": peak_hours,
                "peak_days": peak_days,
                "timezone_estimate": estimate_timezone(peak_hours),
                "session_frequency": "daily" if total_events / total_days > 10 else "weekly",
                "avg_sessions_per_week": round(total_events / (total_days / 7) / 5, 1),
                "avg_articles_per_session": 5.0
            },

            "seasonal_patterns": [
                {
                    "season": "summer",
                    "dominant_topics": ["tour-de-france", "cycling", "outdoor"],
                    "activity_multiplier": 1.5
                },
                {
                    "season": "winter",
                    "dominant_topics": ["ski", "indoor-training", "gear-reviews"],
                    "activity_multiplier": 0.8
                }
            ],

            "cohort_tags": cohort_tags,
            "negative_signals": []  # Would need explicit negative feedback
        },

        "short_term_signals": {
            "user_id": user_id,
            "last_updated": now.isoformat() + "Z",

            "recent_articles": [
                {
                    "article_id": e.get('MESSAGEID', ''),
                    "article_embedding": None,
                    "title": e.get('TITLE', ''),
                    "topics": [],
                    "interaction_timestamp": e.get('TIMESTAMP', ''),
                    "interaction_type": "view",
                    "engagement_score": 0.5
                }
                for e in recent_events[:20]
            ],

            "recent_embedding": None,
            "emerging_topics": emerging_topics,
            "current_session_topics": [],
            "days_since_last_visit": 0,
            "recent_engagement_trend": "stable",
            "relevant_past_interests": ["winter-training", "indoor-cycling"]
        },

        "cohort_attributes": {
            "user_id": user_id,
            "last_updated": now.isoformat() + "Z",

            "engagement_tier": "champion" if engagement_level == "power_user" else "loyal",
            "subscription_status": "active",
            "primary_vertical": "cycling",
            "interest_breadth": "multi-sport",
            "content_consumption_style": "deep_reader",
            "device_preference": "mixed",
            "traffic_source_primary": "direct",
            "predicted_ltv_tier": "high",
            "email_engagement": "highly_engaged" if summary.get('email_traffic_count', 0) > 100 else "moderate",
            "best_contact_time": f"{peak_hours[0]}:00 UTC" if peak_hours else "13:00 UTC",
            "best_contact_day": peak_days[0] if peak_days else "Monday"
        },

        "combined_embedding": None,  # Would blend long_term + short_term embeddings

        "recommendation_weights": {
            "long_term_weight": 0.4,
            "short_term_weight": 0.5,
            "seasonal_weight": 0.1,
            "serendipity_factor": 0.15
        }
    }

    return user_insights


def main():
    # Load data
    print("Loading analysis data...")
    with open('robin_summary.json', 'r') as f:
        summary = json.load(f)
    with open('robin_complete_events.json', 'r') as f:
        events = json.load(f)

    # Extract user ID from first event
    user_id = events[0].get('USERID', 'unknown') if events else 'unknown'
    print(f"Building profile for user: {user_id}")

    # Build insights
    insights = build_user_insights(summary, events, user_id)

    # Save
    output_file = 'robin_user_insights.json'
    with open(output_file, 'w') as f:
        json.dump(insights, f, indent=2, default=str)

    print(f"\nUser insights saved to {output_file}")
    print(f"\nProfile Summary:")
    print(f"  Engagement Level: {insights['long_term_profile']['engagement_level']}")
    print(f"  Cohort Tags: {', '.join(insights['long_term_profile']['cohort_tags'])}")
    print(f"  Top Interests: {', '.join([i['topic'] for i in insights['long_term_profile']['core_interests'][:5]])}")
    print(f"  Peak Hours: {insights['long_term_profile']['temporal_pattern']['peak_hours_utc']}")


if __name__ == "__main__":
    main()
