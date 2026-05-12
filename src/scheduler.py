"""
APScheduler — triggers the pipeline daily at the configured time.
"""
import logging
import signal
import sys

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from pathlib import Path

from src.pipeline import run_pipeline

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"


def _load_schedule() -> tuple[str, str]:
    with open(CONFIG_PATH) as f:
        prefs = yaml.safe_load(f)["preferences"]
    run_time = prefs.get("run_time", "07:00")
    timezone = prefs.get("timezone", "America/New_York")
    hour, minute = run_time.split(":")
    return hour, minute, timezone


def start_scheduler():
    hour, minute, tz = _load_schedule()
    scheduler = BlockingScheduler(timezone=tz)

    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger(hour=int(hour), minute=int(minute), timezone=tz),
        id="daily_job_run",
        name="Daily Job Discovery",
        misfire_grace_time=300,
        replace_existing=True,
    )

    def _shutdown(signum, frame):
        logger.info("Shutting down scheduler…")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("Scheduler started — daily run at %s:%s %s", hour, minute, tz)
    scheduler.start()
