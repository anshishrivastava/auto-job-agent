"""
Telegram notification service.
Sends the morning digest with inline buttons per job.
Runs a lightweight callback listener for Skip / Force-include actions.
"""
import logging
import os
from pathlib import Path

import httpx

from src.models.schemas import TailoredApplication

logger = logging.getLogger(__name__)

_BASE = "https://api.telegram.org/bot{token}/{method}"


def _api(method: str, token: str, **kwargs) -> dict:
    url = _BASE.format(token=token, method=method)
    resp = httpx.post(url, json=kwargs, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _score_emoji(score: float) -> str:
    if score >= 9.5:
        return "🟢"
    if score >= 9.0:
        return "🔵"
    if score >= 8.8:
        return "🟡"
    return "⚪"


def send_digest(applications: list[TailoredApplication], run_stats: dict):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    total = run_stats.get("total_fetched", 0)
    near = run_stats.get("near_misses", 0)

    header = (
        f"💼 *Job Digest — {run_stats.get('date', 'Today')}*\n"
        f"Scanned {total} jobs · {len(applications)} matched (ATS ≥{run_stats.get('threshold', 8.8)}) · {near} near-misses in email\n"
        f"{'─' * 32}"
    )
    _api("sendMessage", token, chat_id=chat_id, text=header, parse_mode="Markdown")

    for i, app in enumerate(applications, 1):
        job = app.job
        score = app.final_ats_score
        emoji = _score_emoji(score)

        missing_str = ""
        if app.score.missing_keywords:
            missing_str = f"\n⚠️ _Gap: {', '.join(app.score.missing_keywords[:3])}_"

        changes_str = ""
        if app.changes_made:
            changes_str = f"\n✏️ _{'; '.join(app.changes_made[:2])}_"

        msg = (
            f"{emoji} *{i}. {job.title}* — {job.company}\n"
            f"📍 {job.location}"
            + (f" | 💰 {job.salary}" if job.salary else "")
            + (f" | 🕒 {_posted_ago(job.posted_at)}" if job.posted_at else "")
            + f"\n📊 ATS Score: *{score}/10*"
            + f"\n_{app.score.reasoning[:120]}_"
            + missing_str
            + changes_str
            + f"\n\n📎 Referral:\n`{app.referral_messages.connection_request[:200]}`"
        )

        inline_keyboard = {
            "inline_keyboard": [[
                {"text": "🔗 View JD", "url": job.job_url},
                {"text": "⏭ Skip", "callback_data": f"skip:{job.id}"},
            ]]
        }

        _api(
            "sendMessage", token,
            chat_id=chat_id,
            text=msg,
            parse_mode="Markdown",
            reply_markup=inline_keyboard,
            disable_web_page_preview=True,
        )

        # Send PDF as document
        pdf_path = Path(app.tailored_resume_path)
        if pdf_path.exists():
            try:
                with open(pdf_path, "rb") as f:
                    url = _BASE.format(token=token, method="sendDocument")
                    httpx.post(url, data={"chat_id": chat_id, "caption": f"📄 Resume for {job.company}"}, files={"document": f}, timeout=60)
            except Exception as exc:
                logger.warning("Failed to send PDF for %s: %s", job.company, exc)

    if not applications:
        _api("sendMessage", token, chat_id=chat_id,
             text="No jobs above ATS threshold today. Check email for near-misses.")


def _posted_ago(posted_at) -> str:
    if not posted_at:
        return ""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)
    diff = now - posted_at
    hours = int(diff.total_seconds() / 3600)
    if hours < 1:
        return "< 1h ago"
    if hours < 24:
        return f"{hours}h ago"
    return f"{diff.days}d ago"


def send_error_alert(message: str):
    """Send a pipeline error notification."""
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if token and chat_id:
            _api("sendMessage", token, chat_id=chat_id,
                 text=f"⚠️ Job Agent Error:\n{message}", parse_mode="Markdown")
    except Exception:
        pass
