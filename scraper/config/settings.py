from pathlib import Path

# BASE_DIR points to project root (one level up from scraper/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

LOG_DIR = BASE_DIR / "data" / "logs"
RUN_DATA_DIR = BASE_DIR / "data" / "run_data"
COOKIE_DIR = BASE_DIR / "data" / "cookies"
