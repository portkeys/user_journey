# Deep User Insights - System Design

## Executive Summary

This document outlines the architecture for scaling our User Insights system from a prototype (9 users) to production scale (1M+ users). The key insight is that different types of user insights have different freshness requirements and should be computed at different layers of the stack.

---

## Current State Analysis

### What We Built (Prototype)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CURRENT PROTOTYPE ARCHITECTURE                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Kafka Topics              Python Application              Output            │
│  ─────────────             ──────────────────              ──────            │
│                                                                              │
│  ┌──────────────┐         ┌──────────────────┐         ┌──────────────┐    │
│  │ robin_events │────────▶│ kafka_consumer   │────────▶│ events/*.json│    │
│  └──────────────┘         │ (bulk export)    │         └──────────────┘    │
│                           └──────────────────┘                  │           │
│  ┌──────────────┐                                               │           │
│  │ power_user   │─────────────────────────────────────────────▶│           │
│  │ _events      │                                               │           │
│  └──────────────┘                                               ▼           │
│                           ┌──────────────────┐         ┌──────────────┐    │
│                           │ event_analyzer   │◀────────│ Raw Events   │    │
│                           │ (compute stats)  │         └──────────────┘    │
│                           └────────┬─────────┘                              │
│                                    │                                        │
│                                    ▼                                        │
│                           ┌──────────────────┐                              │
│                           │ report_data_     │                              │
│                           │ builder          │                              │
│                           │ (LLM insights)   │                              │
│                           └────────┬─────────┘                              │
│                                    │                                        │
│                                    ▼                                        │
│                           ┌──────────────────┐         ┌──────────────┐    │
│                           │ Haiku + GPT-5    │────────▶│ data/*.json  │    │
│                           │ (narratives)     │         │ (reports)    │    │
│                           └──────────────────┘         └──────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Current Python Computations

| Component | What It Computes | Scalability Issue |
|-----------|------------------|-------------------|
| `kafka_consumer.py` | Bulk event export | Must read ALL events for each user |
| `event_analyzer.py` | Tag counts, publication counts, temporal patterns, engagement metrics | Recomputes from scratch each time |
| `report_data_builder.py` | LLM narratives, recent activity extraction | Expensive LLM calls per user |
| `emoji_generator.py` | Avatar suggestion from interests | Lightweight, scales fine |

### Key Problem

**With 1M users, we cannot:**
1. Re-read all raw events on demand (TB of data)
2. Recompute all stats from scratch (hours of processing)
3. Call LLMs for every user frequently (cost + latency)

---

## Insight Freshness Requirements

Different insights have fundamentally different freshness needs:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INSIGHT FRESHNESS SPECTRUM                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  REAL-TIME              SHORT-TERM              LONG-TERM                   │
│  (seconds)              (hours/days)            (weeks/months)              │
│  ──────────             ────────────            ─────────────               │
│                                                                              │
│  • Current session      • Recent spotlight      • Core interests            │
│    interests            • Weekly trends         • Yearly narrative          │
│  • "Just read"          • Emerging interests    • Engagement tier           │
│  • Live activity        • Content preferences   • User persona              │
│    feed                                         • Long-term embedding       │
│                                                                              │
│  ────────────────────────────────────────────────────────────────────────── │
│                                                                              │
│  COMPUTE AT:            COMPUTE AT:             COMPUTE AT:                 │
│  Stream Layer           Triggered Service       Batch Pipeline              │
│  (ksqlDB)               (Event-driven)          (Scheduled Jobs)            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Proposed Architecture: Hybrid Stream + Batch

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PRODUCTION ARCHITECTURE (1M+ Users)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                           RAW EVENT STREAM                                   │
│                           ════════════════                                   │
│                                  │                                           │
│                    ┌─────────────┴─────────────┐                            │
│                    │                           │                             │
│                    ▼                           ▼                             │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐          │
│  │      LAYER 1: STREAM        │  │      LAYER 2: STORAGE       │          │
│  │      (Confluent Cloud)      │  │      (Data Lake)            │          │
│  │                             │  │                             │          │
│  │  ksqlDB Materialized Views: │  │  Raw events archived to:    │          │
│  │  • user_event_counts        │  │  • S3/GCS (Parquet)         │          │
│  │  • user_tag_counts          │  │  • Partitioned by user_id   │          │
│  │  • user_recent_50           │  │  • Retained for batch       │          │
│  │  • user_session_state       │  │    reprocessing             │          │
│  │                             │  │                             │          │
│  └──────────────┬──────────────┘  └─────────────────────────────┘          │
│                 │                                                           │
│                 │  Compacted Topics                                         │
│                 │  (user_stats_v1)                                          │
│                 │                                                           │
│                 ▼                                                           │
│  ┌─────────────────────────────────────────────────────────────┐           │
│  │                   LAYER 3: SERVING                          │           │
│  │                   (User Profile Store)                      │           │
│  │                                                             │           │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │           │
│  │  │ PostgreSQL  │    │    Redis    │    │  Pinecone   │    │           │
│  │  │             │    │             │    │             │    │           │
│  │  │ • Profiles  │    │ • Hot cache │    │ • Embeddings│    │           │
│  │  │ • Memories  │    │ • Recent 50 │    │ • Similarity│    │           │
│  │  │ • Cohorts   │    │ • Sessions  │    │   search    │    │           │
│  │  └─────────────┘    └─────────────┘    └─────────────┘    │           │
│  │                                                             │           │
│  └──────────────────────────┬──────────────────────────────────┘           │
│                             │                                               │
│                             ▼                                               │
│  ┌─────────────────────────────────────────────────────────────┐           │
│  │                   LAYER 4: COMPUTE                          │           │
│  │                   (Insight Generation)                      │           │
│  │                                                             │           │
│  │  ┌─────────────────┐    ┌─────────────────┐                │           │
│  │  │ Triggered       │    │ Batch Pipeline  │                │           │
│  │  │ Service         │    │ (Airflow/       │                │           │
│  │  │                 │    │  Databricks)    │                │           │
│  │  │ • On session_end│    │                 │                │           │
│  │  │ • On milestone  │    │ • Weekly core   │                │           │
│  │  │ • Update recent │    │   interests     │                │           │
│  │  │   spotlight     │    │ • Monthly       │                │           │
│  │  │                 │    │   compaction    │                │           │
│  │  │ LLM: Haiku      │    │ • Yearly review │                │           │
│  │  │ (fast, cheap)   │    │                 │                │           │
│  │  │                 │    │ LLM: Opus/GPT-4 │                │           │
│  │  │                 │    │ (quality)       │                │           │
│  │  └─────────────────┘    └─────────────────┘                │           │
│  │                                                             │           │
│  └─────────────────────────────────────────────────────────────┘           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Layer 1: Stream Processing (ksqlDB)

### Move Aggregations to ksqlDB

Instead of computing stats in Python, maintain real-time materialized views:

```sql
-- User event counts (replaces Python counting)
CREATE TABLE user_event_counts AS
SELECT
    user_id,
    COUNT(*) AS total_events,
    COUNT_DISTINCT(DATE(timestamp)) AS active_days,
    MAX(timestamp) AS last_event_at,
    MIN(timestamp) AS first_event_at
FROM events_stream
GROUP BY user_id
EMIT CHANGES;

-- User tag counts (replaces Python tag aggregation)
CREATE TABLE user_tag_counts AS
SELECT
    user_id,
    tag,
    COUNT(*) AS count
FROM events_stream
CROSS JOIN UNNEST(tags) AS tag
GROUP BY user_id, tag
EMIT CHANGES;

-- User publication counts
CREATE TABLE user_publication_counts AS
SELECT
    user_id,
    domain,
    COUNT(*) AS count
FROM events_stream
GROUP BY user_id, domain
EMIT CHANGES;

-- Recent 50 events per user (windowed)
CREATE TABLE user_recent_events AS
SELECT
    user_id,
    COLLECT_LIST(event) AS recent_events
FROM events_stream
WINDOW TUMBLING (SIZE 7 DAYS)
GROUP BY user_id
EMIT CHANGES;

-- Temporal patterns (hour of day)
CREATE TABLE user_hourly_patterns AS
SELECT
    user_id,
    EXTRACT(HOUR FROM timestamp) AS hour,
    COUNT(*) AS count
FROM events_stream
GROUP BY user_id, EXTRACT(HOUR FROM timestamp)
EMIT CHANGES;
```

### Output: Compacted Topic

```sql
-- Single compacted topic with all user stats
CREATE TABLE user_stats_snapshot AS
SELECT
    ec.user_id,
    ec.total_events,
    ec.active_days,
    ec.last_event_at,
    -- Top 10 tags as JSON array
    (SELECT ARRAY_AGG(tag ORDER BY count DESC LIMIT 10)
     FROM user_tag_counts tc WHERE tc.user_id = ec.user_id) AS top_tags,
    -- Top 5 publications
    (SELECT ARRAY_AGG(domain ORDER BY count DESC LIMIT 5)
     FROM user_publication_counts pc WHERE pc.user_id = ec.user_id) AS top_publications
FROM user_event_counts ec
EMIT CHANGES;
```

### Benefits

| Before (Python) | After (ksqlDB) |
|-----------------|----------------|
| Read all events on demand | Stats pre-computed, always current |
| O(n) per user query | O(1) lookup |
| Minutes to compute | Milliseconds to read |
| Single-threaded | Distributed, parallel |

---

## Layer 3: Serving Layer (User Profile Store)

### PostgreSQL Schema

```sql
-- Core user profile
CREATE TABLE user_profiles (
    user_id UUID PRIMARY KEY,

    -- Identity
    display_name TEXT,
    slug TEXT UNIQUE,
    timezone_offset INT,
    location TEXT,
    avatar_emoji TEXT,

    -- Real-time stats (synced from ksqlDB)
    total_events BIGINT DEFAULT 0,
    active_days INT DEFAULT 0,
    last_event_at TIMESTAMP,
    first_event_at TIMESTAMP,

    -- Computed insights
    engagement_tier TEXT,  -- 'champion', 'loyal', 'casual', 'dormant'
    interest_breadth TEXT, -- 'specialist', 'multi-sport', 'explorer'

    -- Top interests (synced from ksqlDB, denormalized for fast access)
    top_tags JSONB,        -- [{"tag": "cycling", "count": 500}, ...]
    top_publications JSONB,
    temporal_patterns JSONB,

    -- Embeddings (computed weekly)
    long_term_embedding VECTOR(768),
    short_term_embedding VECTOR(768),
    embedding_updated_at TIMESTAMP,

    -- Memory compaction tracking
    memory_compacted_through DATE,

    -- Cohort tags for marketing
    cohort_tags TEXT[],    -- ['cyclist', 'gear-enthusiast', 'weekend-reader']

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_profiles_engagement ON user_profiles(engagement_tier);
CREATE INDEX idx_profiles_cohorts ON user_profiles USING GIN(cohort_tags);
CREATE INDEX idx_profiles_embedding ON user_profiles USING ivfflat(long_term_embedding);
```

### Memory Compaction Table

```sql
-- Compacted memories (one per time period per user)
CREATE TABLE user_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(user_id),

    -- Period definition
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    period_type TEXT NOT NULL,  -- 'month', 'quarter', 'year'

    -- Aggregated stats for the period
    event_count INT,
    top_tags JSONB,
    top_publications JSONB,
    temporal_patterns JSONB,

    -- LLM-generated content
    narrative TEXT,
    key_moments JSONB,     -- [{"date": "...", "title": "...", "significance": "..."}]
    interest_evolution JSONB,

    -- Metadata
    generated_at TIMESTAMP DEFAULT NOW(),
    llm_model TEXT,        -- 'claude-haiku-4.5', 'gpt-5-nano'

    UNIQUE(user_id, period_start, period_type)
);

-- Index for efficient period queries
CREATE INDEX idx_memories_user_period ON user_memories(user_id, period_start DESC);
```

### Redis Cache Schema

```
# Hot user profile (TTL: 1 hour)
user:{user_id}:profile -> JSON blob of frequently accessed fields

# Recent 50 events (TTL: 24 hours, updated by stream)
user:{user_id}:recent -> List of recent event summaries

# Current session state (TTL: 30 minutes)
user:{user_id}:session -> Current session interests, last activity

# Real-time spotlight (TTL: 24 hours, updated on session_end)
user:{user_id}:spotlight -> "This week you've been exploring..."
```

---

## Layer 4: Compute Services

### Triggered Service (Event-Driven)

```python
# triggered_insights_service.py
"""
Listens to specific events and triggers insight updates.
Runs as a lightweight Kafka consumer.
"""

class TriggeredInsightsService:

    def __init__(self):
        self.redis = Redis()
        self.db = PostgreSQL()
        self.llm = HaikuClient()  # Fast, cheap model

    async def on_session_end(self, user_id: str, session_events: list):
        """
        Triggered when user session ends (30 min inactivity).
        Updates: recent spotlight, session-based interests.
        """
        # Generate quick spotlight using Haiku
        spotlight = await self.llm.generate_spotlight(session_events[-20:])

        # Update Redis cache
        await self.redis.set(
            f"user:{user_id}:spotlight",
            spotlight,
            ttl=86400  # 24 hours
        )

    async def on_milestone(self, user_id: str, milestone_type: str):
        """
        Triggered on achievements: 100th article, 1 year anniversary, etc.
        """
        achievement = await self.generate_achievement(user_id, milestone_type)
        await self.db.insert_achievement(user_id, achievement)

    async def on_new_interest_detected(self, user_id: str, new_tag: str):
        """
        Triggered when user engages with a new topic category.
        Updates: emerging interests.
        """
        await self.db.add_emerging_interest(user_id, new_tag)
```

### Batch Pipeline (Scheduled)

```python
# batch_insights_pipeline.py
"""
Scheduled jobs for expensive computations.
Runs on Airflow/Databricks.
"""

class BatchInsightsPipeline:

    @scheduled(cron="0 0 * * 0")  # Weekly, Sunday midnight
    async def update_core_interests(self):
        """
        Weekly job: Recompute core interests for all users.
        """
        users = await self.db.get_users_needing_update()

        for batch in chunk(users, size=100):
            # Read aggregated stats from ksqlDB (not raw events!)
            stats = await self.ksql.get_user_stats(batch)

            # Compute core interests
            for user_id, user_stats in stats.items():
                core = self.compute_core_interests(user_stats)
                await self.db.update_core_interests(user_id, core)

    @scheduled(cron="0 0 1 * *")  # Monthly, 1st of month
    async def compact_memories(self):
        """
        Monthly job: Compact previous month into memory block.
        """
        last_month = get_last_month_range()
        users = await self.db.get_users_with_activity(last_month)

        for user_id in users:
            # Get aggregated stats for the month (from ksqlDB snapshot)
            month_stats = await self.ksql.get_user_month_stats(user_id, last_month)

            # Generate narrative using quality LLM
            narrative = await self.opus.generate_month_narrative(month_stats)

            # Store compacted memory
            await self.db.insert_memory(
                user_id=user_id,
                period_start=last_month.start,
                period_end=last_month.end,
                period_type='month',
                stats=month_stats,
                narrative=narrative
            )

            # Update compaction watermark
            await self.db.update_compaction_watermark(user_id, last_month.end)

    @scheduled(cron="0 0 1 1 *")  # Yearly, Jan 1st
    async def generate_year_in_review(self):
        """
        Yearly job: Generate comprehensive year-in-review.
        """
        year = get_last_year()
        users = await self.db.get_active_users(year)

        for user_id in users:
            # Read compacted monthly memories (not raw events!)
            monthly_memories = await self.db.get_user_memories(
                user_id,
                period_type='month',
                year=year
            )

            # Synthesize year narrative from monthly memories
            year_review = await self.opus.generate_year_review(monthly_memories)

            # Store year memory
            await self.db.insert_memory(
                user_id=user_id,
                period_type='year',
                narrative=year_review
            )
```

---

## Memory Compaction Pattern

### The Key Insight

**Never re-read raw events for long-term insights. Instead, synthesize from compacted memories.**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MEMORY COMPACTION TIMELINE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Raw Events (Kafka/S3)          Compacted Memories (PostgreSQL)             │
│  ─────────────────────          ────────────────────────────────            │
│                                                                              │
│  2024-01: ████████████  ──▶  ┌─────────────────────────────────┐           │
│  2024-02: ██████████    ──▶  │ Q1 2024 Memory                  │           │
│  2024-03: ████████████  ──▶  │ "You discovered trail running   │           │
│                              │  and read 45 articles about     │           │
│                              │  ultramarathons..."             │           │
│                              └─────────────────────────────────┘           │
│                                              │                              │
│  2024-04: ██████        ──▶  ┌──────────────┴──────────────────┐           │
│  2024-05: ████████      ──▶  │ Q2 2024 Memory                  │           │
│  2024-06: ██████████    ──▶  │ "Summer brought a shift to      │           │
│                              │  cycling content, especially    │           │
│                              │  Tour de France coverage..."    │           │
│                              └─────────────────────────────────┘           │
│                                              │                              │
│                                              ▼                              │
│                              ┌─────────────────────────────────┐           │
│                              │ 2024 YEAR MEMORY                │           │
│                              │ (Synthesized from Q1-Q4)        │           │
│                              │                                 │           │
│                              │ "Your 2024 journey with Outside │           │
│                              │  was defined by your evolution  │           │
│                              │  from a casual runner to a      │           │
│                              │  multi-sport enthusiast..."     │           │
│                              └─────────────────────────────────┘           │
│                                                                              │
│  ════════════════════════════════════════════════════════════════          │
│  CURRENT WINDOW (Live)                                                      │
│  ════════════════════════════════════════════════════════════════          │
│                                                                              │
│  2025-01-01 to Present:                                                     │
│  ┌────────────────────────────────────────────────────────────┐            │
│  │ Real-time aggregations in ksqlDB                          │            │
│  │ • Tag counts updating continuously                        │            │
│  │ • Recent 50 events maintained                             │            │
│  │ • Session state tracked                                   │            │
│  └────────────────────────────────────────────────────────────┘            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Query Patterns

```python
# For recent insights (last 7 days):
async def get_recent_insights(user_id: str):
    # Read from Redis/ksqlDB - fast, real-time
    return await redis.get(f"user:{user_id}:recent")

# For long-term insights (core interests):
async def get_long_term_insights(user_id: str):
    # Read from PostgreSQL - pre-computed, stable
    profile = await db.get_profile(user_id)
    return profile.core_interests

# For year-in-review:
async def get_year_review(user_id: str, year: int):
    # Read compacted memory - LLM narrative already generated
    memory = await db.get_memory(user_id, period_type='year', year=year)
    return memory.narrative

# For full journey (efficient!):
async def get_full_journey(user_id: str):
    # Combine: compacted memories + current window
    past_memories = await db.get_all_memories(user_id)  # Already synthesized
    current_stats = await ksql.get_current_stats(user_id)  # Real-time
    return merge(past_memories, current_stats)
```

---

## Downstream Use Cases

### API Design for Different Consumers

```yaml
# Recommendations Service (needs real-time)
GET /api/v1/users/{user_id}/interests/recent
Response:
  recent_tags: ["cycling", "tour-de-france", "tadej-pogacar"]
  session_topics: ["race-results", "stage-analysis"]
  embedding: [0.12, -0.34, ...]  # For similarity search

# Marketing Service (needs cohorts)
GET /api/v1/cohorts/cyclists/members
Response:
  users: [
    {user_id: "...", engagement_tier: "champion", location: "Colorado"},
    ...
  ]
  count: 45230

# Email Personalization (needs weekly digest)
GET /api/v1/users/{user_id}/digest/weekly
Response:
  spotlight: "This week you explored winter cycling gear..."
  recommended_articles: [...]
  stats: {articles_read: 12, new_topics: 2}

# Year-in-Review (needs annual synthesis)
GET /api/v1/users/{user_id}/review/2025
Response:
  narrative: "Your 2025 Outside journey began with..."
  highlights: [...]
  stats: {total_articles: 1234, favorite_topic: "cycling"}
```

### Data Flow by Use Case

| Use Case | Data Source | Update Trigger | Latency |
|----------|-------------|----------------|---------|
| Content Recommendations | Redis (recent) + Pinecone (embedding) | Real-time | <100ms |
| "Recently Read" widget | Redis (recent_50) | Stream | <1s |
| Marketing Cohorts | PostgreSQL (cohort_tags) | Daily batch | 24h |
| Personalized Newsletter | PostgreSQL (core_interests) | Weekly batch | 7d |
| Year-in-Review | PostgreSQL (user_memories) | Annual batch | 1y |
| Churn Prediction | PostgreSQL (engagement_tier + temporal) | Daily batch | 24h |

---

## Implementation Phases

### Phase 1: Stream Aggregations (4-6 weeks)
- Set up ksqlDB materialized views for basic counts
- Create compacted `user_stats` topic
- Build sync service: ksqlDB → PostgreSQL
- **Outcome**: Real-time stats without reading raw events

### Phase 2: Serving Layer (4-6 weeks)
- Deploy PostgreSQL with user_profiles schema
- Set up Redis for hot cache
- Build User Profile API
- **Outcome**: Fast profile lookups for downstream services

### Phase 3: Triggered Updates (4-6 weeks)
- Implement session_end detection
- Build triggered insights service
- Integrate Haiku for real-time spotlights
- **Outcome**: Dynamic recent insights

### Phase 4: Memory Compaction (6-8 weeks)
- Build monthly compaction pipeline
- Implement memory synthesis with Opus/GPT-4
- Create compaction watermark tracking
- **Outcome**: Efficient long-term storage

### Phase 5: Year-in-Review (4 weeks)
- Build annual synthesis pipeline
- Design user-facing review experience
- **Outcome**: Spotify Wrapped-style feature

---

## Cost Considerations

### Current (Prototype)
- Kafka: ~$50/month (low volume)
- LLM: ~$10/month (9 users, occasional regeneration)
- Hosting: Free (GitHub Pages)

### Production (1M Users)

| Component | Estimated Monthly Cost |
|-----------|----------------------|
| Confluent Cloud (ksqlDB) | $2,000-5,000 |
| PostgreSQL (RDS) | $500-1,000 |
| Redis (ElastiCache) | $200-500 |
| Pinecone (embeddings) | $70-200 |
| LLM - Triggered (Haiku) | $500-1,000 |
| LLM - Batch (Opus) | $1,000-2,000 |
| Compute (ECS/Lambda) | $300-500 |
| **Total** | **$4,500-10,000/month** |

### Cost Optimization Strategies
1. **Tiered processing**: Only run expensive LLM synthesis for active users
2. **Caching**: Heavy Redis caching reduces database load
3. **Batching**: Batch LLM calls to reduce per-request overhead
4. **Model selection**: Use Haiku for real-time, Opus for quality batch jobs

---

## Confluent Cloud vs Amazon MSK: Platform Comparison

### Our Workload (Napkin Math)

| Metric | Value |
|--------|-------|
| Event throughput | ~300k events/hour |
| Daily events | ~7.2M events/day |
| Monthly events | ~216M events/month |
| **Historical data** | **~3.68 TB (1 year)** |
| Average event size | ~1.4 KB |
| Monthly data ingress | ~300 GB |
| Number of topics | ~10-20 |
| Consumer groups | ~5-10 |

**Note**: 3.68 TB of historical data is substantial. This makes storage costs and data transfer a major consideration.

### Platform Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     STREAMING PLATFORM COMPARISON                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CONFLUENT CLOUD                        AMAZON MSK                          │
│  ════════════════                       ══════════                          │
│                                                                              │
│  ┌─────────────────┐                    ┌─────────────────┐                 │
│  │ Managed Kafka   │                    │ Managed Kafka   │                 │
│  │ (Multi-cloud)   │                    │ (AWS only)      │                 │
│  └────────┬────────┘                    └────────┬────────┘                 │
│           │                                      │                          │
│           ▼                                      ▼                          │
│  ┌─────────────────┐                    ┌─────────────────┐                 │
│  │ ksqlDB          │                    │ Amazon Managed  │                 │
│  │ (Native SQL     │                    │ Flink           │                 │
│  │  streaming)     │                    │ (Apache Flink)  │                 │
│  └─────────────────┘                    └─────────────────┘                 │
│           │                                      │                          │
│           ▼                                      ▼                          │
│  ┌─────────────────┐                    ┌─────────────────┐                 │
│  │ Schema Registry │                    │ AWS Glue Schema │                 │
│  │ (Native)        │                    │ Registry        │                 │
│  └─────────────────┘                    └─────────────────┘                 │
│           │                                      │                          │
│           ▼                                      ▼                          │
│  ┌─────────────────┐                    ┌─────────────────┐                 │
│  │ Connectors      │                    │ MSK Connect     │                 │
│  │ (200+ managed)  │                    │ (Self-managed)  │                 │
│  └─────────────────┘                    └─────────────────┘                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Cost Comparison (Estimated)

#### Confluent Cloud Pricing

| Component | Our Usage | Estimated Cost |
|-----------|-----------|----------------|
| **Basic Cluster** | 300k events/hr, 300GB/mo ingress | ~$600-900/month |
| **Storage** | 3.68 TB retention | ~$400-600/month |
| **ksqlDB** | 4-8 CSUs (processing units) | ~$1,600-2,400/month |
| **Schema Registry** | Included | $0 |
| **Connectors** | 2-3 managed connectors | ~$200-400/month |
| **Data Transfer** | ~300GB egress to AWS | ~$150-300/month |
| **Total** | | **~$2,950-4,600/month** |

#### Amazon MSK Pricing

| Component | Our Usage | Estimated Cost |
|-----------|-----------|----------------|
| **MSK Serverless** | 300k events/hr, 300GB/mo | ~$500-800/month |
| **MSK Provisioned** (alt) | 3x kafka.m5.large | ~$800-1,000/month |
| **Storage (S3 tiered)** | 3.68 TB (tiered to S3) | ~$100-200/month |
| **Amazon Managed Flink** | 4 KPUs | ~$400-600/month |
| **Glue Schema Registry** | Free tier likely | ~$0-50/month |
| **MSK Connect** | Self-managed on EC2 | ~$100-200/month |
| **Data Transfer** | Within AWS = free | $0 |
| **Total (Serverless)** | | **~$1,100-1,850/month** |
| **Total (Provisioned)** | | **~$1,400-2,050/month** |

#### Cost Summary

```
┌────────────────────────────────────────────────────────────────┐
│                    MONTHLY COST COMPARISON                      │
│                    (3.68 TB historical data)                    │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Confluent Cloud (with ksqlDB)     ████████████████████ $3,800 │
│                                                                 │
│  Amazon MSK Serverless + Flink     ████████████        $1,500  │
│                                                                 │
│  Amazon MSK Provisioned + Flink    ██████████████      $1,700  │
│                                                                 │
│  Potential Savings: ~$2,000-2,300/month (~55-60%)              │
│  Annual Savings: ~$24,000-28,000/year                          │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

#### Why MSK is Cheaper at This Scale

1. **Storage**: MSK supports tiered storage to S3 (~$0.023/GB vs Confluent ~$0.10/GB)
2. **Data Transfer**: No egress costs when staying within AWS
3. **Flink vs ksqlDB**: Managed Flink pricing more predictable than CSU-based ksqlDB

---

### Cost Calculation Details & Sources

#### Our Workload Assumptions

```
Event throughput:     300,000 events/hour
                    = 7,200,000 events/day
                    = 216,000,000 events/month

Historical storage:   3.68 TB (1 year of data)

Average event size:   3.68 TB / (216M × 12 months) ≈ 1.4 KB/event

Monthly ingress:      216M events × 1.4 KB = ~300 GB/month
```

#### Confluent Cloud Calculation

**Source**: [Confluent Cloud Pricing](https://www.confluent.io/confluent-cloud/pricing/) (January 2026)

| Component | Calculation | Monthly Cost |
|-----------|-------------|--------------|
| **Kafka Cluster (Basic)** | ~$1/GB ingress + base fee | |
| - Ingress | 300 GB × $1.00/GB | $300 |
| - Base cluster | Standard tier | ~$300-400 |
| - Partition hours | ~50 partitions × 720 hrs × $0.004 | ~$144 |
| **Subtotal Cluster** | | **~$750** |
| | | |
| **Storage** | | |
| - Confluent storage | 3.68 TB × ~$0.10/GB/month | ~$370 |
| - Extended retention | Additional for >7 days | ~$100-200 |
| **Subtotal Storage** | | **~$500** |
| | | |
| **ksqlDB** | | |
| - CSU pricing | $0.55/CSU-hour |  |
| - 4 CSUs × 720 hours | 4 × 720 × $0.55 | ~$1,584 |
| - May need 6-8 CSUs for our aggregations | | ~$1,600-2,400 |
| **Subtotal ksqlDB** | | **~$2,000** |
| | | |
| **Connectors** | | |
| - Managed connectors | ~$0.10/task-hour | |
| - 3 connectors × 720 hrs | 3 × 720 × $0.10 | ~$216 |
| **Subtotal Connectors** | | **~$250** |
| | | |
| **Data Transfer (Egress)** | | |
| - To AWS (cross-cloud) | 300 GB × $0.05-0.10/GB | ~$150-300 |
| **Subtotal Egress** | | **~$200** |
| | | |
| **TOTAL CONFLUENT** | | **~$3,700** |

**Note**: ksqlDB is the biggest cost driver. CSU (Confluent Streaming Unit) pricing at $0.55/hour adds up quickly for always-on stream processing.

#### Amazon MSK Calculation

**Sources**:
- [Amazon MSK Pricing](https://aws.amazon.com/msk/pricing/) (January 2026)
- [Amazon Managed Flink Pricing](https://aws.amazon.com/managed-service-apache-flink/pricing/)
- [S3 Pricing](https://aws.amazon.com/s3/pricing/)

| Component | Calculation | Monthly Cost |
|-----------|-------------|--------------|
| **MSK Serverless** | | |
| - Cluster hours | $0.75/hour × 720 hours | $540 |
| - Storage (hot) | ~500 GB × $0.10/GB | $50 |
| - Partition hours | 50 × 720 × $0.0015 | $54 |
| - Data in | 300 GB × $0.10/GB | $30 |
| - Data out | 300 GB × $0.05/GB | $15 |
| **Subtotal MSK** | | **~$700** |
| | | |
| **Tiered Storage (S3)** | | |
| - 3.68 TB in S3 Standard | 3,680 GB × $0.023/GB | ~$85 |
| - Or S3 Infrequent Access | 3,680 GB × $0.0125/GB | ~$46 |
| **Subtotal S3** | | **~$50-85** |
| | | |
| **Amazon Managed Flink** | | |
| - KPU pricing | $0.11/KPU-hour | |
| - 4 KPUs × 720 hours | 4 × 720 × $0.11 | ~$317 |
| - Running storage | 50 GB × $0.10/GB | ~$5 |
| - Durable storage | 100 GB × $0.023/GB | ~$2.30 |
| **Subtotal Flink** | | **~$350** |
| | | |
| **Glue Schema Registry** | | |
| - Free tier: 1M schemas | Likely covered | $0 |
| **Subtotal Schema** | | **~$0** |
| | | |
| **MSK Connect** | | |
| - Self-managed on EC2 | t3.medium × 2 | ~$60 |
| - Or Fargate | 0.5 vCPU × 2 × 720 hrs | ~$50 |
| **Subtotal Connect** | | **~$60** |
| | | |
| **Data Transfer** | | |
| - Within AWS (same region) | | $0 |
| **Subtotal Transfer** | | **$0** |
| | | |
| **TOTAL MSK** | | **~$1,200** |

#### Key Cost Differences Explained

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      WHERE THE SAVINGS COME FROM                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. STREAM PROCESSING                                                        │
│     ksqlDB:  4 CSUs × $0.55/hr × 720 hrs = $1,584/month                     │
│     Flink:   4 KPUs × $0.11/hr × 720 hrs = $317/month                       │
│     SAVINGS: ~$1,267/month (80% cheaper)                                    │
│                                                                              │
│  2. STORAGE (3.68 TB)                                                        │
│     Confluent: ~$0.10/GB = $368/month (all on Kafka storage)                │
│     MSK+S3:    ~$0.023/GB = $85/month (tiered to S3)                        │
│     SAVINGS: ~$283/month (77% cheaper)                                      │
│                                                                              │
│  3. DATA TRANSFER                                                            │
│     Confluent → AWS: ~$0.05-0.10/GB egress                                  │
│     Within AWS: $0                                                           │
│     SAVINGS: ~$150-300/month (100% cheaper)                                 │
│                                                                              │
│  TOTAL MONTHLY SAVINGS: ~$1,700-1,850                                       │
│  TOTAL ANNUAL SAVINGS:  ~$20,000-22,000                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Caveats & Assumptions

1. **Pricing as of January 2026** - Cloud pricing changes frequently
2. **Estimates only** - Actual costs depend on exact usage patterns
3. **ksqlDB CSUs** - May need more/fewer depending on query complexity
4. **Flink KPUs** - Auto-scaling could increase costs during spikes
5. **MSK Serverless** - Pricing varies by region; used us-east-1 estimates
6. **Not included**:
   - AWS Support plans
   - Monitoring/logging costs (CloudWatch)
   - Development/migration labor costs
7. **Tiered storage assumption**: Assumes ~90% of 3.68 TB is >7 days old and can tier to S3

#### Recommended Next Step

Run the **AWS Pricing Calculator** with your exact workload:
- https://calculator.aws/#/addService/MSK
- https://calculator.aws/#/addService/KinesisDataAnalytics (for Managed Flink)

And compare with **Confluent Cost Estimator**:
- https://www.confluent.io/confluent-cloud/pricing/ (cost calculator at bottom)

### Feature Comparison

| Feature | Confluent Cloud | Amazon MSK |
|---------|-----------------|------------|
| **Managed Kafka** | ✅ Fully managed | ✅ Fully managed |
| **Stream Processing** | ksqlDB (SQL-native) | Amazon Managed Flink (Java/SQL) |
| **Ease of Use** | ⭐⭐⭐⭐⭐ (ksqlDB is very easy) | ⭐⭐⭐ (Flink has learning curve) |
| **Schema Registry** | ✅ Native, excellent | ✅ Glue (adequate) |
| **Connectors** | ✅ 200+ fully managed | ⚠️ MSK Connect (self-managed) |
| **Multi-cloud** | ✅ AWS, GCP, Azure | ❌ AWS only |
| **AWS Integration** | ⚠️ Requires setup | ✅ Native (IAM, VPC, etc.) |
| **Monitoring** | ✅ Built-in dashboards | ✅ CloudWatch |
| **Support** | ✅ Dedicated | ✅ AWS Support |

### Stream Processing: ksqlDB vs Amazon Managed Flink

This is the critical comparison for our use case.

#### ksqlDB (Confluent)

```sql
-- Example: User tag counts (what we need)
CREATE TABLE user_tag_counts AS
SELECT
    user_id,
    tag,
    COUNT(*) AS count
FROM events_stream
LATERAL JOIN UNNEST(tags) AS tag
GROUP BY user_id, tag
EMIT CHANGES;
```

**Pros:**
- Pure SQL syntax - very easy to learn
- Native Kafka integration
- Built-in materialized views
- Pull queries for point lookups
- Great for simple aggregations

**Cons:**
- Limited to SQL operations
- Complex joins can be tricky
- ksqlDB clusters can get expensive at scale
- Proprietary to Confluent

#### Amazon Managed Flink

```java
// Example: User tag counts in Flink SQL
tableEnv.executeSql("""
    CREATE TABLE user_tag_counts (
        user_id STRING,
        tag STRING,
        cnt BIGINT,
        PRIMARY KEY (user_id, tag) NOT ENFORCED
    ) WITH (
        'connector' = 'upsert-kafka',
        'topic' = 'user-tag-counts',
        ...
    )
""");

tableEnv.executeSql("""
    INSERT INTO user_tag_counts
    SELECT user_id, tag, COUNT(*) as cnt
    FROM events_table
    CROSS JOIN UNNEST(tags) AS t(tag)
    GROUP BY user_id, tag
""");
```

**Or using Flink SQL (simpler):**

```sql
-- Amazon Managed Flink also supports SQL
CREATE TABLE user_tag_counts AS
SELECT
    user_id,
    tag,
    COUNT(*) AS cnt
FROM events_table
CROSS JOIN UNNEST(tags) AS t(tag)
GROUP BY user_id, tag;
```

**Pros:**
- More powerful (full programming language available)
- Better for complex event processing
- Exactly-once semantics
- Can output to multiple sinks (S3, DynamoDB, etc.)
- Flink SQL is quite similar to ksqlDB
- Open source (no vendor lock-in)

**Cons:**
- Steeper learning curve than ksqlDB
- More configuration required
- Need to manage state backends
- Flink SQL is good but less polished than ksqlDB

### What We Need for Stream Processing

| Computation | ksqlDB | Flink | Verdict |
|-------------|--------|-------|---------|
| Tag counts per user | ✅ Easy | ✅ Easy | Both work |
| Publication counts | ✅ Easy | ✅ Easy | Both work |
| Temporal patterns | ✅ Easy | ✅ Easy | Both work |
| Recent N events | ✅ Windowed table | ✅ Windowed table | Both work |
| Session detection | ⚠️ Possible | ✅ Native support | Flink better |
| Complex CEP (event patterns) | ❌ Limited | ✅ Full CEP library | Flink better |
| Output to multiple sinks | ⚠️ Connectors | ✅ Native | Flink better |

**Verdict**: For our use case (basic aggregations), both work well. Flink is more powerful but ksqlDB is easier.

### AWS Integration Benefits

If we move to MSK, we gain:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AWS ECOSYSTEM INTEGRATION                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  MSK ──▶ Amazon Managed Flink ──▶ Multiple Outputs:                         │
│                                                                              │
│                                   ┌─────────────────┐                       │
│                               ┌──▶│ Amazon RDS      │ (User profiles)       │
│                               │   └─────────────────┘                       │
│                               │                                             │
│                               │   ┌─────────────────┐                       │
│                               ├──▶│ ElastiCache     │ (Hot cache)           │
│                               │   └─────────────────┘                       │
│                               │                                             │
│                               │   ┌─────────────────┐                       │
│                               ├──▶│ S3              │ (Archive)             │
│                               │   └─────────────────┘                       │
│                               │                                             │
│                               │   ┌─────────────────┐                       │
│                               └──▶│ OpenSearch      │ (Search)              │
│                                   └─────────────────┘                       │
│                                                                              │
│  Benefits:                                                                   │
│  • No data transfer costs within AWS                                        │
│  • Native IAM authentication                                                │
│  • VPC integration (private networking)                                     │
│  • Unified billing                                                          │
│  • CloudWatch metrics/logs                                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Migration Path: Confluent → MSK

#### Phase 1: Parallel Run (2-4 weeks)
1. Set up MSK cluster in same VPC as other AWS services
2. Set up MirrorMaker 2 to replicate topics from Confluent → MSK
3. Test consumers against MSK

#### Phase 2: Flink Development (4-6 weeks)
1. Rewrite ksqlDB queries as Flink SQL
2. Test materialized views output to Kafka compacted topics
3. Verify data consistency

#### Phase 3: Cutover (1-2 weeks)
1. Switch producers to MSK
2. Verify all consumers working
3. Decommission Confluent Cloud

### Recommendation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           RECOMMENDATION                                     │
│                     (Updated for 3.68 TB data volume)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  SHORT-TERM (Next 3 months):                                                │
│  ═══════════════════════════                                                │
│  Start MSK migration planning NOW                                           │
│  • At 3.68 TB, storage costs alone justify migration                        │
│  • $24-28k/year savings is significant                                      │
│  • Begin Flink SQL prototyping in parallel                                  │
│                                                                              │
│  MEDIUM-TERM (3-6 months):                                                  │
│  ══════════════════════════                                                 │
│  Execute migration:                                                         │
│  • Set up MSK cluster with tiered storage to S3                             │
│  • Migrate stream processing to Amazon Managed Flink                        │
│  • Run parallel for 2-4 weeks, then cut over                                │
│                                                                              │
│  LONG-TERM (6+ months):                                                     │
│  ═════════════════════                                                      │
│  Fully AWS-native stack:                                                    │
│  • MSK + Flink + RDS + ElastiCache + S3                                     │
│  • Unified billing, IAM, VPC                                                │
│  • No cross-cloud data transfer costs                                       │
│                                                                              │
│  ════════════════════════════════════════════════════════════════          │
│                                                                              │
│  WHY MIGRATE SOONER (with 3.68 TB):                                         │
│  • Storage: Confluent ~$400-600/mo vs MSK+S3 ~$100-200/mo                   │
│  • Egress: ~$150-300/mo to move data to AWS vs $0 within AWS               │
│  • At this scale, savings compound quickly                                  │
│  • Migration effort (~8-12 weeks) pays back in <6 months                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Quick Reference: Equivalent Tools

| Confluent Cloud | Amazon MSK Equivalent |
|-----------------|----------------------|
| ksqlDB | Amazon Managed Flink (Flink SQL) |
| Schema Registry | AWS Glue Schema Registry |
| Managed Connectors | MSK Connect + self-managed |
| Confluent Control Center | Amazon CloudWatch + MSK Console |
| Confluent CLI | AWS CLI + kafka-cli |

---

## Open Questions

1. **Retention Policy**: How long to keep raw events vs. rely on compacted memories?
2. **Privacy**: PII handling in embeddings and LLM-generated narratives?
3. **Multi-tenancy**: Should this be a shared service or per-publication?
4. **Backfill**: How to generate memories for historical users who joined before system launch?

---

## Appendix: Migration from Prototype

### What to Keep
- `event_analyzer.py` logic → Move to batch pipeline
- `emoji_generator.py` → Keep as utility
- `report_data_builder.py` → Refactor for triggered service

### What to Replace
- `kafka_consumer.py` (bulk read) → ksqlDB continuous aggregation
- JSON file output → PostgreSQL + Redis
- Manual regeneration → Automated pipelines

### What to Add
- ksqlDB materialized views
- PostgreSQL schema
- Redis caching layer
- Triggered insights service
- Airflow DAGs for batch jobs

---

*Document created: January 15, 2026*
*Author: User Insights Architecture Team*
