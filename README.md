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
| Trevor | Canada | 39,088 | [View](https://portkeys.github.io/user_journey/report.html?user=trevor) |
| Kate | Seattle | 4,525 | [View](https://portkeys.github.io/user_journey/report.html?user=kate) |
| Wen | Berkeley | 2,470 | [View](https://portkeys.github.io/user_journey/report.html?user=wen) |
| PJ | Colorado | 150 | [View](https://portkeys.github.io/user_journey/report.html?user=pj) |
| Kcal | Texas | 1,225 | [View](https://portkeys.github.io/user_journey/report.html?user=kcal) |
| Dan | Connecticut | 162 | [View](https://portkeys.github.io/user_journey/report.html?user=dan) |

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
```

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
│   └── batch_generate.py
└── docs/
    ├── USER_JOURNEY_PIPELINE.md
    └── PHASE2_PROPOSAL.md
```

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
