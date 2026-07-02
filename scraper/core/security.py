SECURITY_KEYWORDS = [
    "captcha",
    "cloudflare",
    "verify you are human",
    "security check",
    "access denied",
    "too many requests",
    "human verification",
    "人机验证",
    "安全验证",
    "访问过于频繁",
    "请完成安全检查",
]


def is_security_check_page(page) -> bool:
    text = getattr(page, "text", "") or ""

    if callable(text):
        text = text() or ""

    if not text and hasattr(page, "css"):
        try:
            text = " ".join(page.css("body ::text, body::text").getall())
        except Exception:
            text = ""

    if not text and hasattr(page, "xpath"):
        try:
            text = " ".join(page.xpath("//text()").getall())
        except Exception:
            text = ""

    lower_text = str(text).lower()

    return any(keyword.lower() in lower_text for keyword in SECURITY_KEYWORDS)
