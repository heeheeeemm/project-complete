import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent / '06_pipeline'
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

from run_pipeline import run_pipeline  # noqa: E402


def analyze_company(company, include_summary=False):
    """기존 06_pipeline 코드를 Django에서 호출한다."""
    return run_pipeline(
        company,
        limit=20,
        criteria_name='strict',
        headless=True,
        summarize=include_summary,
    )
