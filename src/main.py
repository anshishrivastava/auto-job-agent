"""
Entry point.

Usage:
  python -m src.main            # run once immediately
  python -m src.main --schedule # run on daily schedule (keeps process alive)
  python -m src.main --dry-run  # fetch + score but skip PDF/notifications
"""
import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.logging import RichHandler

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="%H:%M:%S",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )


def _check_env():
    required = ["ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
                "EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"[ERROR] Missing environment variables: {', '.join(missing)}")
        print("Copy .env.example → .env and fill in your credentials.")
        sys.exit(1)


def main():
    _setup_logging()

    parser = argparse.ArgumentParser(description="Job Discovery Agent")
    parser.add_argument("--schedule", action="store_true", help="Run on daily schedule")
    parser.add_argument("--dry-run", action="store_true", help="Fetch + score only, no PDFs or notifications")
    args = parser.parse_args()

    if not args.dry_run:
        _check_env()

    if args.schedule:
        from src.scheduler import start_scheduler
        start_scheduler()
    else:
        from src.pipeline import run_pipeline
        result = run_pipeline(dry_run=args.dry_run)
        print(f"\n✅ Done — {result.passed_ats_threshold} jobs above threshold, {result.near_misses} near-misses")


if __name__ == "__main__":
    main()
