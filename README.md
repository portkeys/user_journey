# Outside User Journey Reports

Personalized "Outside Memory" reports for power users, combining behavioral analytics with LLM-powered insights.

**Live Site**: [portkeys.github.io/user_journey](https://portkeys.github.io/user_journey/)

## Quick Start

```bash
# Install dependencies
uv sync

# Generate a report for a specific user
python scripts/batch_generate.py --user robin

# Generate for all users with event data
python scripts/batch_generate.py

# Start local server for testing
python -m http.server 8080
open http://localhost:8080/
```

## Current Users

| User | Location | Events | Report |
|------|----------|--------|--------|
| Robin | Colorado | 21,354 | [View](https://portkeys.github.io/user_journey/report.html?user=robin) |
| Trevor | Canada | 83,554 | [View](https://portkeys.github.io/user_journey/report.html?user=trevor) |
| Kate | Seattle | 8,363 | [View](https://portkeys.github.io/user_journey/report.html?user=kate) |
| Wen | Berkeley | 6,091 | [View](https://portkeys.github.io/user_journey/report.html?user=wen) |
| PJ | Colorado | 789 | [View](https://portkeys.github.io/user_journey/report.html?user=pj) |
| Kcal | Texas | 3,622 | [View](https://portkeys.github.io/user_journey/report.html?user=kcal) |
| Dan | Connecticut | 5,196 | [View](https://portkeys.github.io/user_journey/report.html?user=dan) |
| Lauren | New York | 8,766 | [View](https://portkeys.github.io/user_journey/report.html?user=lauren) |
| Mike | North Carolina | 3,402 | [View](https://portkeys.github.io/user_journey/report.html?user=mike) |

## Architecture

```
Kafka Topics ──> Consumer Scripts ──> Event Analysis ──> LLM Insights ──> JSON Data ──> HTML Report
                                                              │
                                                    Claude Haiku + GPT-5-nano
```

## Key Commands

### Kafka Consumers

```bash
# Single user (Robin's dedicated topic)
python kafka_consumer.py robin_complete_events.json

# Multi-user topic (splits by user_id)
python scripts/multi_user_consumer.py

# Check topic info
python scripts/multi_user_consumer.py --info
```

### Report Generation

```bash
# Generate for specific user
python scripts/batch_generate.py --user trevor

# Generate for all users
python scripts/batch_generate.py

# Skip LLM calls (for testing)
python scripts/batch_generate.py --user trevor --skip-llm

# Auto-generate emojis based on activity/location
python scripts/batch_generate.py --auto-emoji
```

### Smart Emoji Generator

The system can automatically suggest avatar emojis based on user activity or location:

```bash
# Test emoji suggestion for a user
python scripts/emoji_generator.py --summary-file data/robin.json --location "Colorado"

# Output: Emoji: 🚴  Reason: Based on top activity: tour-de-france
```

Emoji selection strategy:
- **Activity-first** (default): Picks emoji based on top activity tags (cycling, running, skiing, etc.)
- **Location-first**: Uses location emoji if no activity match (🏔️ Colorado, 🌧️ Seattle, etc.)
- Reports include both `avatar_emoji` and `suggested_emoji` with reasoning

## File Structure

```
user_journey/
├── index.html              # Landing page (user selector)
├── report.html             # Dynamic report template
├── data/
│   ├── users.json          # User registry
│   ├── robin.json          # Pre-computed report data
│   └── ...
├── events/                  # Raw event files (gitignored)
├── scripts/
│   ├── multi_user_consumer.py
│   ├── event_analyzer.py
│   ├── report_data_builder.py
│   ├── batch_generate.py
│   └── emoji_generator.py
└── docs/
    ├── USER_JOURNEY_PIPELINE.md
    └── PHASE2_PROPOSAL.md
```

## Updating Reports with New Data

When new events are available in Kafka (e.g., after replay catches up):

```bash
# Step 1: Re-consume events from Kafka (gets latest data)
python scripts/multi_user_consumer.py

# Step 2: Regenerate all reports
python scripts/batch_generate.py

# Step 3: Commit and push
git add data/*.json
git commit -m "Update reports with latest data"
git push
```

**Check if replay is complete:**
```bash
python scripts/multi_user_consumer.py --info
```

The consumer always re-consumes from the beginning, ensuring you get the complete dataset.

## Adding a New User

1. Add user to `data/users.json`
2. Export events from Kafka (or run multi_user_consumer)
3. Generate report: `python scripts/batch_generate.py --user <slug>`
4. Commit and push `data/<slug>.json`

## Documentation

- [Pipeline Guide](docs/USER_JOURNEY_PIPELINE.md) - Step-by-step guide
- [Phase 2 Proposal](docs/PHASE2_PROPOSAL.md) - Future infrastructure plans

## Tech Stack

- **Kafka**: Confluent Cloud (event streaming)
- **LLMs**: Claude Haiku 4.5 (Bedrock) + GPT-5-nano (OpenAI)
- **Visualization**: Chart.js
- **Hosting**: GitHub Pages

---

Built by Wen Yang + Claude Opus 4.5
