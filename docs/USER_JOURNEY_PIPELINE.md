# User Journey Analysis Pipeline

> **Status**: Demo Complete (Robin) | **Next**: Production Pipeline
> **Demo Report**: [https://your-username.github.io/user_journey/](https://your-username.github.io/user_journey/)

## Overview

This document outlines the process for generating personalized user journey reports from Kafka event streams. The pipeline combines behavioral analytics with LLM-powered insights to create rich, shareable HTML reports.

### What We Built

An end-to-end system that:
1. Consumes user events from Confluent Cloud Kafka
2. Analyzes behavioral patterns across the Outside ecosystem
3. Generates LLM-powered narratives and insights
4. Produces an interactive HTML report with visualizations

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Confluent      │     │  Python          │     │  LLM APIs       │
│  Cloud Kafka    │────▶│  Analysis        │────▶│  (GPT-5-nano,   │
│  (Event Stream) │     │  Scripts         │     │   Claude Haiku) │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                │                        │
                                ▼                        ▼
                        ┌──────────────────┐     ┌─────────────────┐
                        │  JSON Summary    │     │  Narratives &   │
                        │  & Metrics       │     │  Insights       │
                        └──────────────────┘     └─────────────────┘
                                │                        │
                                └───────────┬────────────┘
                                            ▼
                                ┌──────────────────────┐
                                │  Interactive HTML    │
                                │  Report (Chart.js)   │
                                └──────────────────────┘
```

---

## Data Sources

### Kafka Event Stream

- **Cluster**: Confluent Cloud
- **Authentication**: SASL_SSL with API key/secret
- **Event Format**: JSON with standardized fields

### Key Event Fields

| Field | Description | Example |
|-------|-------------|---------|
| `USER_ID` | Unique user identifier | `robin_demo_user` |
| `TIMESTAMP` | ISO 8601 with timezone | `2024-03-15T14:30:00Z` |
| `EVENT_NAME` | Action type | `page_view`, `video_play` |
| `URL` | Page/content URL | `https://trailforks.com/...` |
| `TITLE` | Content title | `Best Mountain Bike Trails...` |
| `DOMAIN` | Source platform | `trailforks.com`, `outsideonline.com` |
| `PLATFORM` | Device/app type | `web`, `ios`, `android` |

### Outside Ecosystem Coverage

| Platform | Event Types | Insights Generated |
|----------|-------------|-------------------|
| **Editorial** | Page views, article reads | Reading patterns, topic interests |
| **Trailforks** | Ride logs, map views, trail lookups | Biking activity, trail preferences |
| **Gaia GPS** | Session starts, map interactions | Outdoor navigation habits |
| **Outside Watch** | Video plays, completions | Video consumption patterns |
| **Outside App** | App opens, feature usage | Mobile engagement |

---

## Pipeline Scripts

### 1. `kafka_consumer.py` - Event Collection

**Purpose**: Bulk export events for a specific user from Kafka.

```bash
# Usage
python kafka_consumer.py --user-id <USER_ID> --output <filename>.json
```

**Configuration** (`.env` file):
```
KAFKA_BOOTSTRAP_SERVERS=pkc-xxxxx.us-west-2.aws.confluent.cloud:9092
KAFKA_API_KEY=your_api_key
KAFKA_API_SECRET=your_api_secret
KAFKA_TOPIC=user_events
```

**Output**: JSON file with all user events (e.g., `robin_complete_events.json`)

---

### 2. `robin_analyzer.py` - Behavioral Analysis

**Purpose**: Process raw events into structured analytics.

**Key Methods**:

| Method | Output |
|--------|--------|
| `get_summary()` | Total events, date range, top domains/pages |
| `get_hourly_distribution()` | Activity by hour (for timezone charts) |
| `get_daily_distribution()` | Activity by day of week |
| `analyze_interests()` | Topic categorization from titles/URLs |
| `analyze_ecosystem_usage()` | Platform-specific metrics |
| `get_recent_activity()` | Latest reads, watches, sessions |

**Usage**:
```python
from robin_analyzer import RobinAnalyzer

analyzer = RobinAnalyzer('user_events.json')
summary = analyzer.get_summary()
ecosystem = analyzer.analyze_ecosystem_usage()
```

**Output**: `robin_summary.json` with aggregated metrics

---

### 3. `llm_analyzer.py` - LLM Narrative Generation

**Purpose**: Generate human-readable insights using LLMs.

**LLM Providers**:

| Model | Provider | Use Case |
|-------|----------|----------|
| Claude Haiku 4.5 | AWS Bedrock | Main narrative, journey story |
| GPT-5-nano | OpenAI API | Structured interest analysis |

**Key Functions**:

```python
# Claude Haiku via AWS Bedrock
def call_haiku(prompt: str) -> str:
    # Returns narrative text

# GPT-5-nano via OpenAI
def call_gpt5_nano(prompt: str) -> dict:
    # Returns structured JSON with:
    # - seasonal_patterns
    # - emerging_interests
    # - core_interests
    # - casual_interests
```

**Configuration** (`.env` file):
```
# AWS Bedrock (Claude Haiku)
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-west-2

# OpenAI (GPT-5-nano)
OPENAI_API_KEY=your_key
```

---

### 4. `generate_report.py` - HTML Report Generation

**Purpose**: Combine analytics and LLM insights into interactive HTML.

**Report Sections**:

1. **Your Outside Ecosystem** - Platform usage cards
2. **Recent Activity Spotlight** - Latest reads, watches, seasonal patterns
3. **Your Interests** - Core vs casual interests, top topics
4. **When You're Most Active** - Hour/day distribution charts
5. **Your Journey with Outside** - LLM-generated narrative

**Usage**:
```bash
python generate_report.py
# Outputs: robin_journey_report.html
```

**Key Features**:
- Chart.js for interactive visualizations
- Timezone conversion (UTC → user's local time)
- Clickable article links with dates
- Responsive card-based layout

---

### 5. `build_user_profile.py` - Structured User Insights

**Purpose**: Generate machine-readable user profile following schema.

**Output Schema** (`schemas/user_insights_schema.json`):
```json
{
  "user_id": "string",
  "profile": {
    "interests": [...],
    "engagement_patterns": {...},
    "ecosystem_usage": {...}
  },
  "insights": {
    "narrative": "string",
    "recommendations": [...]
  }
}
```

---

## Step-by-Step Process

### For a New User

```bash
# 1. Set up environment
cd user_journey
uv sync  # Install dependencies

# 2. Configure credentials
cp .env.example .env
# Edit .env with Kafka and LLM API credentials

# 3. Export user events from Kafka
python kafka_consumer.py --user-id NEW_USER_ID --output new_user_events.json

# 4. Update analyzer to use new file
# Edit robin_analyzer.py: change input filename

# 5. Generate the report
python generate_report.py

# 6. Review output
open new_user_journey_report.html
```

---

## Report Customization

### Timezone Configuration

Reports convert UTC timestamps to user's local timezone:

```python
# In generate_report.py
MT_OFFSET = -7  # Mountain Time (Colorado)

# For other users, adjust offset:
# PST: -8, EST: -5, CST: -6, etc.
```

### Filtering Content

Latest Reads filters out generic titles:

```python
GENERIC_PATTERNS = [
    'home', 'velo -', 'welcome to',
    'outside magazine', '- outside'
]
```

---

## Output Files

| File | Purpose |
|------|---------|
| `*_complete_events.json` | Raw Kafka events (gitignored) |
| `*_summary.json` | Aggregated analytics |
| `*_user_insights.json` | Structured profile data |
| `*_journey_report.html` | Final HTML report |
| `index.html` | GitHub Pages deployment copy |

---

## Future Pipeline (Phase 2)

See [PHASE2_PROPOSAL.md](./PHASE2_PROPOSAL.md) for planned infrastructure:

- **Automated ingestion**: Scheduled Kafka consumers per user
- **Embedding storage**: Vector DB for content similarity
- **Cohort analysis**: Group users by behavior patterns
- **Personalized recommendations**: Based on journey insights
- **Dashboard**: Admin view of all user journeys

---

## Dependencies

```toml
# pyproject.toml
[dependencies]
confluent-kafka = "^2.3.0"
boto3 = "^1.34.0"        # AWS Bedrock
openai = "^1.12.0"       # GPT-5-nano
python-dotenv = "^1.0.0"
```

Install with:
```bash
uv sync
```

---

## Troubleshooting

### Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Empty hour chart | JSON keys are strings | Use `hours.get(str(h), 0)` |
| NoneType in titles | Missing TITLE field | Use `(e.get('TITLE') or 'Untitled')` |
| GPT-5-nano error | Temperature not supported | Remove temperature parameter |
| Kafka timeout | Network/auth issue | Check .env credentials |

---

## Contact

- **Demo built by**: Wen Yang + Claude Opus 4.5
- **Report issues**: GitHub Issues
