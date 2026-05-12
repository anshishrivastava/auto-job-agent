# Job Discovery Agent

Autonomous daily agent that crawls LinkedIn/Indeed/Glassdoor, scores jobs against your resume using a tiered ATS pipeline, tailors your resume per job, and delivers a digest via Telegram + email.

## Architecture

> 📐 Full diagram: [docs/architecture.drawio](docs/architecture.drawio) — open at [app.diagrams.net](https://app.diagrams.net/)

## How it works

```
Fetch jobs (jobspy) → Stage 1: keyword filter → Stage 2: embedding similarity
→ Stage 3: LLM score (Claude Haiku) → Tailor resume (Claude Sonnet) → PDF
→ Telegram digest (top jobs) + Email digest (near-misses)
```

**Cost per daily run:** ~$0.05–0.15 (Claude API) | **Time:** ~60–90 seconds

## Setup

### 1. Install dependencies

```bash
cd job-agent
pip install -e .
```

### 2. Configure credentials

```bash
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
#          EMAIL_SENDER, EMAIL_APP_PASSWORD, EMAIL_RECIPIENT
```

**Telegram setup (5 minutes):**
1. Message `@BotFather` on Telegram → `/newbot` → copy the token
2. Message your new bot once, then run:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/getUpdates"
   ```
   Copy the `chat.id` from the response

**Gmail App Password:**
Google Account → Security → 2-Step Verification → App passwords → generate one

### 3. Update your job preferences

```bash
cp config/config.example.yaml config/config.yaml
# Edit config/config.yaml — set your target roles, locations, salary floor, and ATS threshold
```

### 4. Add your resume

```bash
cp config/resume.example.json config/resume.json
# Replace with your actual resume data — config/resume.json is gitignored and stays local
```

## Running

```bash
# Run once immediately
python -m src.main

# Dry run — fetch + score only, no PDFs or notifications (good for testing)
python -m src.main --dry-run

# Start daily scheduler (keeps process alive, runs at configured time)
python -m src.main --schedule
```

## Output

- PDFs saved to `output/resumes/`
- Job history in `output/jobs.db` (SQLite — open with DB Browser or TablePlus)

## Architecture

```
src/
├── main.py              Entry point (run once or schedule)
├── pipeline.py          Main orchestrator
├── scheduler.py         APScheduler daily trigger
├── models/schemas.py    Data models (JobListing, ATSScore, TailoredApplication)
├── sources/
│   ├── base.py          JobDataSource interface
│   └── jobspy_source.py LinkedIn + Indeed + Glassdoor scraper
├── scoring/
│   ├── keyword.py       Stage 1: keyword match (~10ms, free)
│   ├── embedding.py     Stage 2: semantic similarity (~150ms, free)
│   ├── llm_scorer.py    Stage 3: Claude Haiku holistic score (~3s, ~$0.003)
│   └── pipeline.py      Orchestrates all three stages
├── tailoring/
│   ├── resume_tailor.py Keyword injection via Claude Sonnet
│   ├── pdf_generator.py WeasyPrint HTML→PDF
│   └── referral.py      LinkedIn + email referral message generation
├── notifications/
│   ├── telegram_bot.py  Morning digest with inline buttons
│   └── email_sender.py  Near-miss email digest
└── storage/database.py  SQLite run history + feedback loop
```

## Swapping job sources

The `JobDataSource` interface in `src/sources/base.py` makes it trivial to swap scrapers.
When ready to upgrade to a paid API, implement `JSearchSource` in `src/sources/jsearch_source.py`
and change one line in `pipeline.py`.

## Tests

```bash
pytest tests/ -v
```
