# User Journey Analysis Pipeline

> **Status**: Multi-User Production Ready
> **Live Reports**: [https://portkeys.github.io/user_journey/](https://portkeys.github.io/user_journey/)

## Overview

A multi-user system that generates personalized "Outside Memory" reports from Kafka event streams, combining behavioral analytics with LLM-powered insights.

### Current Users

| User | Slug | Events | Status |
|------|------|--------|--------|
| Robin | `robin` | 21,354 | ✅ Complete |
| Trevor | `trevor` | 39,088 | ✅ Complete |
| Kate | `kate` | 4,525 | Ready |
| Wen | `wen` | 2,470 | Ready |
| Kcal | `kcal` | 1,225 | Ready |
| Dan | `dan` | 162 | Ready |
| PJ | `pj` | 150 | Ready |

---

## Quick Start

### Generate a User's Report

```bash
# Generate report for a specific user
python scripts/batch_generate.py --user trevor

# View in browser
open "http://localhost:8080/report.html?user=trevor"
```

### Generate All Reports

```bash
# Generate for all users with event data
python scripts/batch_generate.py
```

### Start Local Server

```bash
# Start server for local testing
python -m http.server 8080

# Open landing page
open http://localhost:8080/
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        MULTI-USER ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Kafka Topics                                                           │
│  ┌─────────────────┐     ┌─────────────────────┐                       │
│  │ robin_events    │     │ power_user_events   │                       │
│  │ (single user)   │     │ (6 users, keyed)    │                       │
│  └────────┬────────┘     └──────────┬──────────┘                       │
│           │                         │                                   │
│           ▼                         ▼                                   │
│  ┌─────────────────┐     ┌─────────────────────┐                       │
│  │kafka_consumer.py│     │multi_user_consumer  │                       │
│  └────────┬────────┘     └──────────┬──────────┘                       │
│           │                         │                                   │
│           ▼                         ▼                                   │
│  ┌─────────────────┐     ┌─────────────────────┐                       │
│  │robin_complete_  │     │events/              │                       │
│  │events.json      │     │  trevor_events.json │                       │
│  └────────┬────────┘     │  kate_events.json   │                       │
│           │              │  wen_events.json    │                       │
│           │              │  ...                │                       │
│           │              └──────────┬──────────┘                       │
│           └──────────┬──────────────┘                                  │
│                      ▼                                                  │
│           ┌─────────────────────┐                                      │
│           │ batch_generate.py   │                                      │
│           │ + LLM APIs          │                                      │
│           └──────────┬──────────┘                                      │
│                      ▼                                                  │
│           ┌─────────────────────┐     ┌─────────────────────┐         │
│           │ data/               │     │ GitHub Pages        │         │
│           │   users.json        │────▶│   index.html        │         │
│           │   robin.json        │     │   report.html?user= │         │
│           │   trevor.json       │     └─────────────────────┘         │
│           │   ...               │                                      │
│           └─────────────────────┘                                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Step-by-Step Guide

### Step 1: Environment Setup

```bash
# Clone and enter directory
cd user_journey

# Install dependencies
uv sync

# Configure credentials
cp .env.example .env
# Edit .env with your Kafka and LLM API credentials
```

### Step 2: Consume Events from Kafka

**Option A: Single User (Robin's dedicated topic)**
```bash
# For Robin (uses KAFKA_TOPIC from .env)
python kafka_consumer.py robin_complete_events.json
```

**Option B: Multiple Users (power_user_events topic)**
```bash
# Check topic info first
python scripts/multi_user_consumer.py --info

# Consume and split by user_id
python scripts/multi_user_consumer.py

# Output:
#   events/trevor_events.json
#   events/kate_events.json
#   events/wen_events.json
#   ... (auto-updates data/users.json)
```

### Step 3: Generate Reports

**Single User:**
```bash
# Generate for Trevor
python scripts/batch_generate.py --user trevor

# Generate for Kate
python scripts/batch_generate.py --user kate

# Generate for Wen
python scripts/batch_generate.py --user wen

# Skip LLM calls (for quick testing)
python scripts/batch_generate.py --user trevor --skip-llm
```

**All Users:**
```bash
# Generate for everyone with event data
python scripts/batch_generate.py
```

### Step 4: View Reports Locally

```bash
# Start local server
python -m http.server 8080

# View landing page (user selector)
open http://localhost:8080/

# View specific user's report
open "http://localhost:8080/report.html?user=robin"
open "http://localhost:8080/report.html?user=trevor"
open "http://localhost:8080/report.html?user=kate"
```

### Step 5: Deploy to GitHub Pages

```bash
# Commit new report data
git add data/*.json
git commit -m "Add report for trevor"
git push

# Reports are live at:
# https://portkeys.github.io/user_journey/report.html?user=trevor
```

---

## Command Reference

### Kafka Consumers

| Command | Purpose |
|---------|---------|
| `python kafka_consumer.py <output.json>` | Single-user topic (Robin) |
| `python scripts/multi_user_consumer.py` | Multi-user topic (splits by user_id) |
| `python scripts/multi_user_consumer.py --info` | Show topic info without consuming |

### Report Generation

| Command | Purpose |
|---------|---------|
| `python scripts/batch_generate.py` | Generate for all users with data |
| `python scripts/batch_generate.py --user <slug>` | Generate for specific user |
| `python scripts/batch_generate.py --skip-llm` | Skip LLM calls (testing) |

### Local Development

| Command | Purpose |
|---------|---------|
| `python -m http.server 8080` | Start local server |
| `open http://localhost:8080/` | View landing page |
| `open "http://localhost:8080/report.html?user=robin"` | View specific report |

---

## File Structure

```
user_journey/
├── index.html                    # Landing page (user selector)
├── report.html                   # Dynamic report template
├── data/                         # Pre-computed report data
│   ├── users.json               # User registry
│   ├── robin.json               # Robin's report data
│   ├── trevor.json              # Trevor's report data
│   └── ...
├── events/                       # Raw event files (gitignored)
│   ├── trevor_events.json
│   ├── kate_events.json
│   └── ...
├── scripts/                      # Pipeline scripts
│   ├── multi_user_consumer.py   # Kafka consumer for power_user_events
│   ├── event_analyzer.py        # Generic event analyzer
│   ├── report_data_builder.py   # JSON + LLM generation
│   └── batch_generate.py        # CLI tool
├── kafka_consumer.py             # Original single-user consumer
├── robin_complete_events.json    # Robin's events (gitignored)
└── docs/
    ├── USER_JOURNEY_PIPELINE.md  # This file
    └── PHASE2_PROPOSAL.md        # Future infrastructure
```

---

## User Registry

The `data/users.json` file contains user metadata:

```json
{
  "users": [
    {
      "user_id": "uuid-here",
      "display_name": "Trevor",
      "slug": "trevor",
      "timezone_offset": -5,
      "timezone_name": "Eastern Time",
      "location": "New York",
      "avatar_emoji": "🌲",
      "events_file": "events/trevor_events.json"
    }
  ]
}
```

**To add a new user manually:**
1. Add entry to `data/users.json`
2. Place events file in specified location
3. Run `python scripts/batch_generate.py --user <slug>`

---

## Kafka Topics

| Topic | Key | Users | Purpose |
|-------|-----|-------|---------|
| `robin_events` | None | Robin only | Original demo user |
| `power_user_events` | `user_id` | 6 users | Multi-user stream |

### Re-consuming Events

The consumer **re-consumes from the beginning** each time (fresh export). This is intentional for:
- Replay scenarios (KSQL catching up)
- Ensuring complete data

If the `power_user_events` topic is still replaying:
1. Run consumer now → get partial data (good for testing)
2. Run again when replay completes → get full data
3. Regenerate reports with `batch_generate.py`

---

## LLM Configuration

| Model | Provider | Purpose | Config |
|-------|----------|---------|--------|
| Claude Haiku 4.5 | AWS Bedrock | Narrative + Recent Activity | `BEDROCK_MODEL_ID` |
| GPT-5-nano | OpenAI | Structured Interest Analysis | `OPENAI_API_KEY` |

**Cost Estimate per User:**
- Haiku: ~$0.02 (2 calls)
- GPT-5-nano: ~$0.01 (1 call)
- Total: ~$0.03/user

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| "User not found in registry" | Slug not in users.json | Add user to registry or run multi_user_consumer |
| "No events file found" | Missing events JSON | Run appropriate Kafka consumer first |
| Empty charts | No temporal data | Check events have TIMESTAMP field |
| LLM timeout | API rate limit | Wait and retry, or use `--skip-llm` |
| CORS error (local) | Opening file:// directly | Use `python -m http.server 8080` |

---

## Deployment Checklist

- [ ] Events consumed from Kafka
- [ ] User added to `data/users.json` with correct timezone
- [ ] Report generated with `batch_generate.py`
- [ ] Tested locally with `python -m http.server`
- [ ] Committed `data/<slug>.json` (not events files)
- [ ] Pushed to GitHub
- [ ] Verified on GitHub Pages

---

## Contact

- **Built by**: Wen Yang + Claude Opus 4.5
- **Repository**: [github.com/portkeys/user_journey](https://github.com/portkeys/user_journey)
- **Report Issues**: GitHub Issues
