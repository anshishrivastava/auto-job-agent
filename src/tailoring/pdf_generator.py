"""
Renders a tailored resume dict → ATS-friendly PDF via WeasyPrint + Jinja2.
"""
import logging
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"
OUTPUT_DIR = Path(__file__).resolve().parents[3] / "output" / "resumes"


def generate_pdf(resume: dict, job_title: str, company: str, job_id: str) -> str:
    """
    Returns the absolute path to the generated PDF.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("resume.html")
    html_content = template.render(resume=resume, job_title=job_title, company=company)

    safe_company = "".join(c if c.isalnum() else "_" for c in company)[:30]
    safe_title = "".join(c if c.isalnum() else "_" for c in job_title)[:30]
    filename = f"{safe_company}_{safe_title}_{job_id}.pdf"
    out_path = OUTPUT_DIR / filename

    HTML(string=html_content, base_url=str(TEMPLATES_DIR)).write_pdf(str(out_path))
    logger.info("PDF generated: %s", out_path)
    return str(out_path)
