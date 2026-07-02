import os
from pathlib import Path

from dotenv import load_dotenv

# BASE_DIR now points to project root (one level up from scraper/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# 根据 APP_ENV 加载对应配置文件
# APP_ENV=dev -> .env.dev
# APP_ENV=production 或未设置 -> .env
APP_ENV = os.getenv("APP_ENV", "production")
env_file = f".env.{APP_ENV}" if APP_ENV != "production" else ".env"
load_dotenv(BASE_DIR / env_file, override=True)

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
USE_DYNAMIC_FETCHER = os.getenv("USE_DYNAMIC_FETCHER", "false").lower() == "true"

MAX_LIST_PAGES = min(int(os.getenv("MAX_LIST_PAGES", "50")), 50)
LIST_PAGE_DELAY_MIN = float(os.getenv("LIST_PAGE_DELAY_MIN", "4"))
LIST_PAGE_DELAY_MAX = float(os.getenv("LIST_PAGE_DELAY_MAX", "5"))
DETAIL_PAGE_DELAY_MIN = float(os.getenv("DETAIL_PAGE_DELAY_MIN", "2"))
DETAIL_PAGE_DELAY_MAX = float(os.getenv("DETAIL_PAGE_DELAY_MAX", "3"))
SECURITY_WAIT_SECONDS = float(os.getenv("SECURITY_WAIT_SECONDS", "120"))
INCREMENTAL_EXIST_THRESHOLD = int(os.getenv("INCREMENTAL_EXIST_THRESHOLD", "0"))
LOG_DIR = BASE_DIR / "data" / "logs"
RUN_DATA_DIR = BASE_DIR / "data" / "run_data"
COOKIE_DIR = BASE_DIR / "data" / "cookies"
