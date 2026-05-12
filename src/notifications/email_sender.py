"""
Email digest for near-miss jobs (scored between near_miss_min and ats_threshold).
Uses Gmail SMTP with an App Password.
"""
import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.models.schemas import ATSScore, JobListing

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"


def send_near_miss_digest(
    near_misses: list[tuple[JobListing, ATSScore]],
    run_date: str,
    threshold: float,
):
    if not near_misses:
        return

    sender = os.environ["EMAIL_SENDER"]
    password = os.environ["EMAIL_APP_PASSWORD"]
    recipient = os.environ["EMAIL_RECIPIENT"]

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("email_digest.html")
    html_body = template.render(
        near_misses=near_misses,
        run_date=run_date,
        threshold=threshold,
        count=len(near_misses),
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📋 Job Near-Misses — {run_date} ({len(near_misses)} jobs, scores below {threshold})"
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
        logger.info("Near-miss email sent: %d jobs", len(near_misses))
    except Exception as exc:
        logger.error("Failed to send near-miss email: %s", exc)
