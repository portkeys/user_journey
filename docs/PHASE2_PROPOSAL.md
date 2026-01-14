# Phase 2 Proposal: User Insights Infrastructure

## Executive Summary

Build a scalable user insights infrastructure that transforms raw event data into actionable user profiles for personalization, recommendations, and marketing.

---

## Phase 1 Deliverables (Complete)

| Deliverable | Status | Output |
|-------------|--------|--------|
| Kafka Consumer | ✅ | `kafka_consumer.py` - Bulk export of 21K+ events |
| Event Analysis | ✅ | `robin_analyzer.py` - Comprehensive data analysis |
| LLM Integration | ✅ | Haiku 4.5 + GPT-5-nano comparison |
| HTML Report | ✅ | `robin_journey_report.html` - Shareable user journey |
| Schema Design | ✅ | `schemas/user_insights_schema.json` |
| Profile Builder | ✅ | `build_user_profile.py` - Transform to schema |

---

## Phase 2: User Insights Infrastructure

### 2.1 User Profile Embeddings

**Objective**: Generate vector embeddings that capture user interests for similarity search and recommendations.

#### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER EMBEDDING PIPELINE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Raw Events   │───▶│ Topic        │───▶│ User Profile │      │
│  │ (Kafka)      │    │ Extraction   │    │ Embedding    │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                   │              │
│                                                   ▼              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Article      │───▶│ Similarity   │───▶│ Personalized │      │
│  │ Embeddings   │    │ Search       │    │ Recs         │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Embedding Strategy

1. **Long-Term Interest Embedding** (768-dim)
   - Aggregate user's top topics over 90+ days
   - Weight by engagement frequency and recency
   - Update: Weekly batch job

2. **Short-Term Interest Embedding** (768-dim)
   - Weighted average of last 50 article embeddings
   - Time-decay weighting (recent = higher weight)
   - Update: Daily or real-time

3. **Combined Embedding** (768-dim)
   - Blend: `0.4 * long_term + 0.5 * short_term + 0.1 * seasonal`
   - User-specific weights based on behavior patterns

#### Technical Implementation

```python
# Embedding model options
EMBEDDING_MODELS = {
    "production": "text-embedding-3-large",  # OpenAI, 3072-dim
    "cost_effective": "text-embedding-3-small",  # OpenAI, 1536-dim
    "on_prem": "sentence-transformers/all-mpnet-base-v2",  # 768-dim
}

# User embedding computation
def compute_user_embedding(user_insights: UserInsights) -> np.ndarray:
    # Aggregate topic embeddings weighted by interest score
    topic_embeddings = [
        get_topic_embedding(interest.topic) * interest.score
        for interest in user_insights.long_term_profile.core_interests
    ]
    return normalize(np.mean(topic_embeddings, axis=0))
```

---

### 2.2 Recommendation System Integration

**Objective**: Enable real-time personalized recommendations using the user insights schema.

#### Recommendation Strategies

| Strategy | Description | When to Use |
|----------|-------------|-------------|
| **Content-Based** | Match user embedding to article embeddings | Default |
| **Collaborative** | Users with similar profiles liked X | Cold start |
| **Seasonal** | Re-circulate past seasonal content | Time-based |
| **Serendipity** | Introduce controlled randomness | Prevent filter bubble |

#### API Design

```yaml
# Recommendation Request
POST /api/v1/recommendations
{
  "user_id": "f03f8762-bd4b-42dc-a989-800836b1bd7e",
  "context": {
    "current_article_id": "abc123",  # For "more like this"
    "session_topics": ["cycling", "gear"],
    "exclude_ids": ["already-read-1", "already-read-2"]
  },
  "config": {
    "count": 10,
    "strategy": "blended",  # or "content", "collaborative", "seasonal"
    "diversity_factor": 0.2
  }
}

# Response
{
  "recommendations": [
    {
      "article_id": "xyz789",
      "title": "Best Winter Cycling Gear 2025",
      "score": 0.92,
      "reason": "Based on your interest in cycling and gear reviews"
    }
  ],
  "strategy_used": "blended",
  "embedding_version": "2025-01-13"
}
```

---

### 2.3 Marketing Cohort System

**Objective**: Enable data-driven segmentation for campaigns.

#### Cohort Definitions

```yaml
cohorts:
  engagement_based:
    - champion: "engagement_tier == 'champion' AND days_since_last_visit < 7"
    - at_risk: "engagement_tier == 'loyal' AND days_since_last_visit > 14"
    - dormant: "days_since_last_visit > 30"
    - winback: "engagement_tier == 'dormant' AND seasonal_match == true"

  interest_based:
    - cyclists: "'cyclist' IN cohort_tags"
    - multi_sport: "interest_breadth == 'multi-sport'"
    - gear_enthusiasts: "'gear-enthusiast' IN cohort_tags"

  behavioral:
    - newsletter_engaged: "email_engagement IN ('highly_engaged', 'moderate')"
    - app_users: "device_preference IN ('app', 'mobile')"
    - weekend_readers: "'Saturday' IN peak_days OR 'Sunday' IN peak_days"
```

#### Cohort API

```yaml
# Query cohort members
GET /api/v1/cohorts/cyclists/members?limit=1000

# Get user's cohorts
GET /api/v1/users/{user_id}/cohorts

# Cohort statistics
GET /api/v1/cohorts/cyclists/stats
{
  "cohort": "cyclists",
  "member_count": 45230,
  "avg_engagement": 42.5,
  "top_content": ["tour-de-france", "gear-reviews"],
  "best_send_time": "Tuesday 8:00 AM MT"
}
```

---

### 2.4 Real-Time Profile Updates

**Objective**: Keep user profiles current with streaming updates.

#### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    REAL-TIME UPDATE FLOW                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Kafka Events  ──▶  Flink/Spark  ──▶  Profile Updates           │
│       │              Streaming           │                       │
│       │                                  ▼                       │
│       │              ┌─────────────────────────────┐            │
│       │              │  Redis (Hot Profile Cache)  │            │
│       │              └─────────────────────────────┘            │
│       │                                  │                       │
│       ▼                                  ▼                       │
│  ┌──────────────┐              ┌──────────────────┐             │
│  │ Data Lake    │              │ PostgreSQL       │             │
│  │ (Raw Events) │              │ (User Profiles)  │             │
│  └──────────────┘              └──────────────────┘             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Update Triggers

| Event Type | Profile Update | Latency |
|------------|----------------|---------|
| Page View | Add to recent_articles | Real-time |
| Session End | Recompute short_term_embedding | < 1 min |
| Daily Batch | Update engagement metrics | Nightly |
| Weekly Batch | Recompute long_term_embedding | Weekly |

---

### 2.5 Dynamic Visualization Generation

**Objective**: Use LLM to generate custom Chart.js visualizations based on user data.

#### Concept

```python
def generate_dynamic_charts(user_insights: dict) -> list[dict]:
    """
    Use LLM to analyze user data and generate appropriate
    Chart.js configurations dynamically.
    """
    prompt = """
    Analyze this user's interest evolution data and generate
    2-3 Chart.js configurations that best visualize their journey.

    Consider:
    - Interest trajectory over time
    - Seasonal patterns
    - Topic distribution changes
    - Engagement trends

    Return valid Chart.js config JSON for each visualization.
    """

    response = llm.generate(prompt, user_insights)
    return parse_chart_configs(response)
```

#### Example Output

```javascript
// LLM-generated chart for user's cycling interest trajectory
{
  type: 'line',
  data: {
    labels: ['Jan', 'Feb', 'Mar', ...],
    datasets: [{
      label: 'Tour de France Interest',
      data: [10, 15, 20, 45, 180, 200, ...],  // Spike during Tour
      borderColor: '#FFD100'
    }]
  }
}
```

---

## Implementation Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| 2.1 Embeddings | 2-3 sprints | Embedding pipeline, vector DB integration |
| 2.2 Recommendations | 2 sprints | Rec API, A/B testing framework |
| 2.3 Cohorts | 1-2 sprints | Cohort service, marketing integrations |
| 2.4 Real-Time | 2-3 sprints | Streaming pipeline, cache layer |
| 2.5 Dynamic Viz | 1 sprint | LLM chart generation |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Recommendation CTR | +15% | A/B test vs current |
| Email Campaign CTR | +20% | Cohort-targeted vs blast |
| User Engagement | +10% | Pages/session with personalization |
| Profile Freshness | < 24h | Time from event to profile update |

---

## Dependencies

- **Vector Database**: Pinecone, Weaviate, or pgvector
- **Streaming**: Kafka Streams, Flink, or Spark Structured Streaming
- **Cache**: Redis for hot profile serving
- **LLM**: Haiku 4.5 (Bedrock) for dynamic content generation

---

## Open Questions

1. **Embedding Model**: OpenAI vs self-hosted? Cost vs latency tradeoff
2. **Profile Storage**: PostgreSQL + pgvector vs dedicated vector DB?
3. **Update Frequency**: How fresh do short-term signals need to be?
4. **Privacy**: PII handling in embeddings and cohort data?

---

## Future Ideas

### Auto-Generated Avatar Emoji

Select user avatar emoji based on their top interests from the insights data:

```python
def suggest_avatar(summary: dict) -> str:
    """Auto-select emoji based on user's top interests"""
    top_tags = list(summary.get('tags', {}).keys())[:10]

    EMOJI_MAP = {
        ('cycling', 'biking', 'mtb', 'gravel', 'road cycling'): '🚴',
        ('running', 'trail running', 'marathon', 'ultrarunning'): '🏃',
        ('skiing', 'backcountry', 'alpine', 'ski touring'): '⛷️',
        ('climbing', 'bouldering', 'rock climbing'): '🧗',
        ('hiking', 'backpacking', 'thru-hiking'): '🥾',
        ('swimming', 'triathlon', 'open water'): '🏊',
        ('yoga', 'meditation', 'wellness'): '🧘',
        ('camping', 'overlanding', 'van life'): '🏕️',
    }

    for keywords, emoji in EMOJI_MAP.items():
        if any(tag in keywords for tag in top_tags):
            return emoji

    return '🏔️'  # Default outdoor emoji
```

Could be integrated into `report_data_builder.py` to auto-suggest avatars during report generation.

---

## Next Steps

1. Review schema with engineering team
2. Set up vector DB POC
3. Design A/B test framework for recommendations
4. Define cohort taxonomy with marketing

---

*Document created: January 13, 2026*
*Author: User Journey Analysis Team*
