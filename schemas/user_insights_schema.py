"""
User Insights Schema Design
For downstream applications: recommendations, cohorts, marketing, personalization

This schema separates:
1. Long-term profile (stable interests, updated weekly/monthly)
2. Short-term signals (recent activity, updated daily)
3. Behavioral patterns (engagement habits)
4. Cohort attributes (for segmentation)
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from enum import Enum


class InterestStrength(Enum):
    """How strong is the user's interest in a topic"""
    CORE = "core"           # Consistent, high engagement over time
    ACTIVE = "active"       # Regular engagement, current interest
    CASUAL = "casual"       # Occasional engagement
    DORMANT = "dormant"     # Was interested, not recently active
    EMERGING = "emerging"   # New, growing interest


@dataclass
class TopicInterest:
    """A single topic/interest with strength and evidence"""
    topic: str                          # Normalized topic name (e.g., "cycling", "tour-de-france")
    strength: InterestStrength
    score: float                        # 0.0 to 1.0, computed from engagement
    first_seen: datetime                # When user first engaged with this topic
    last_seen: datetime                 # Most recent engagement
    engagement_count: int               # Total interactions with this topic
    trend: str                          # "rising", "stable", "declining"


@dataclass
class ContentPreference:
    """User's content format preferences"""
    format: str                         # "long-reads", "reviews", "how-to", "news", "video"
    preference_score: float             # 0.0 to 1.0
    avg_engagement_depth: float         # How deeply they engage (time, scroll, etc.)


@dataclass
class AuthorAffinity:
    """User's relationship with specific authors"""
    author_name: str
    articles_read: int
    affinity_score: float               # 0.0 to 1.0


@dataclass
class TemporalPattern:
    """When and how the user engages"""
    peak_hours_utc: list[int]           # Top 3 most active hours
    peak_days: list[str]                # Top 3 most active days
    timezone_estimate: str              # Estimated user timezone
    session_frequency: str              # "daily", "weekly", "sporadic"
    avg_sessions_per_week: float
    avg_articles_per_session: float


@dataclass
class SeasonalPattern:
    """Seasonal interest variations"""
    season: str                         # "winter", "spring", "summer", "fall"
    dominant_topics: list[str]          # Topics that spike in this season
    activity_multiplier: float          # How much more/less active vs baseline


# ============================================================
# LONG-TERM PROFILE (Updated weekly/monthly)
# ============================================================

@dataclass
class UserLongTermProfile:
    """
    Stable user profile for embedding generation and long-term personalization.
    Updated weekly or monthly to capture enduring interests.

    Use cases:
    - Generate user embedding vector for recommendations
    - Identify user archetypes/personas
    - Long-term content strategy
    """
    user_id: str
    profile_version: str                # Schema version for migrations
    last_updated: datetime

    # Core interests (stable over time)
    core_interests: list[TopicInterest]           # Top 10-20 strongest interests
    interest_embedding: Optional[list[float]]      # Pre-computed 768/1536-dim vector

    # Content preferences
    preferred_publications: list[str]              # Ranked list
    content_preferences: list[ContentPreference]
    favorite_authors: list[AuthorAffinity]

    # Engagement profile
    engagement_level: str               # "power_user", "regular", "casual", "churning"
    lifetime_events: int
    account_age_days: int
    avg_monthly_events: float

    # Temporal DNA
    temporal_pattern: TemporalPattern
    seasonal_patterns: list[SeasonalPattern]

    # Cohort tags (for segmentation)
    cohort_tags: list[str]              # e.g., ["cyclist", "gear-enthusiast", "weekend-warrior"]

    # For recommendations: topics to avoid (low engagement despite exposure)
    negative_signals: list[str]


# ============================================================
# SHORT-TERM SIGNALS (Updated daily)
# ============================================================

@dataclass
class RecentArticleInteraction:
    """A recent article the user interacted with"""
    article_id: str
    article_embedding: Optional[list[float]]       # Pre-computed article vector
    title: str
    topics: list[str]
    interaction_timestamp: datetime
    interaction_type: str               # "view", "read", "share", "save"
    engagement_score: float             # 0.0 to 1.0 based on time spent, scroll depth


@dataclass
class UserShortTermSignals:
    """
    Recent activity for real-time personalization.
    Updated daily or on each session.

    Use cases:
    - Real-time recommendation blending
    - "Continue reading" / "Because you read..."
    - Trending topic detection for user
    """
    user_id: str
    last_updated: datetime

    # Recent interactions (last 7-30 days)
    recent_articles: list[RecentArticleInteraction]  # Last 50-100 articles
    recent_embedding: Optional[list[float]]           # Weighted average of recent article embeddings

    # Emerging interests (new topics in last 30 days)
    emerging_topics: list[TopicInterest]

    # Session context
    current_session_topics: list[str]    # Topics in current/last session

    # Recency signals
    days_since_last_visit: int
    recent_engagement_trend: str         # "increasing", "stable", "decreasing"

    # For seasonal recirculation
    relevant_past_interests: list[str]   # Dormant interests that match current season


# ============================================================
# COHORT ATTRIBUTES (For marketing/segmentation)
# ============================================================

@dataclass
class UserCohortAttributes:
    """
    Attributes for marketing segmentation and cohort analysis.

    Use cases:
    - Email campaign targeting
    - A/B test segmentation
    - Churn prediction
    - Upsell/cross-sell targeting
    """
    user_id: str
    last_updated: datetime

    # Engagement cohorts
    engagement_tier: str                # "champion", "loyal", "at_risk", "dormant", "new"
    subscription_status: str            # "active", "lapsed", "never"

    # Interest-based cohorts
    primary_vertical: str               # "cycling", "running", "outdoor", "wellness"
    interest_breadth: str               # "specialist", "multi-sport", "explorer"

    # Behavioral cohorts
    content_consumption_style: str      # "deep_reader", "scanner", "video_first"
    device_preference: str              # "mobile", "desktop", "app"
    traffic_source_primary: str         # "direct", "email", "search", "social"

    # Value signals
    predicted_ltv_tier: str             # "high", "medium", "low"
    email_engagement: str               # "highly_engaged", "moderate", "low", "unsubscribed"

    # Timing
    best_contact_time: str              # "morning", "afternoon", "evening"
    best_contact_day: str


# ============================================================
# COMBINED USER INSIGHTS (Full profile for API)
# ============================================================

@dataclass
class UserInsights:
    """
    Complete user insights object combining all components.
    This is the main object returned by the User Insights API.
    """
    user_id: str
    generated_at: datetime
    schema_version: str = "1.0.0"

    long_term_profile: UserLongTermProfile
    short_term_signals: UserShortTermSignals
    cohort_attributes: UserCohortAttributes

    # Recommendation inputs (pre-computed for fast serving)
    combined_embedding: Optional[list[float]]      # Blend of long-term + short-term
    recommendation_weights: dict                    # How to blend long vs short term


# ============================================================
# EXAMPLE USAGE
# ============================================================

EXAMPLE_ROBIN_INSIGHTS = {
    "user_id": "f03f8762-bd4b-42dc-a989-800836b1bd7e",
    "generated_at": "2026-01-13T15:00:00Z",
    "schema_version": "1.0.0",

    "long_term_profile": {
        "core_interests": [
            {"topic": "professional-cycling", "strength": "core", "score": 0.95},
            {"topic": "tour-de-france", "strength": "core", "score": 0.92},
            {"topic": "trail-running", "strength": "active", "score": 0.75},
            {"topic": "national-parks", "strength": "active", "score": 0.68},
            {"topic": "gear-reviews", "strength": "active", "score": 0.65},
        ],
        "preferred_publications": ["VeloNews", "outside-online", "Trailforks"],
        "favorite_authors": ["Jim Cotton", "Andrew Hood", "Shane Stokes"],
        "engagement_level": "power_user",
        "temporal_pattern": {
            "peak_hours_utc": [13, 18, 14],
            "peak_days": ["Monday", "Tuesday", "Wednesday"],
            "timezone_estimate": "America/Denver",
        },
        "cohort_tags": ["cyclist", "endurance-athlete", "gear-enthusiast"],
    },

    "short_term_signals": {
        "recent_articles": [
            # Last 7 days of article interactions with embeddings
        ],
        "emerging_topics": ["winter-training", "indoor-cycling"],
        "days_since_last_visit": 0,
        "recent_engagement_trend": "stable",
        "relevant_past_interests": ["ski-touring"],  # Winter seasonal
    },

    "cohort_attributes": {
        "engagement_tier": "champion",
        "primary_vertical": "cycling",
        "interest_breadth": "multi-sport",
        "content_consumption_style": "deep_reader",
        "email_engagement": "highly_engaged",
    },

    "recommendation_weights": {
        "long_term_weight": 0.4,
        "short_term_weight": 0.5,
        "seasonal_weight": 0.1,
    }
}
