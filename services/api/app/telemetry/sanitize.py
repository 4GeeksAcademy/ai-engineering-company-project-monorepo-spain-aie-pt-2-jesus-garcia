import re

MAX_STRING_LENGTH = 300

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "new_password",
        "current_password",
        "hashed_password",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "secret",
        "api_key",
        "jwt",
    }
)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
_PHONE_RE = re.compile(r"(\+\d[\d\s().-]{6,}\d)|(\b\d{2,4}[\s.-]\d{2,4}[\s.-]\d{2,4}\b)")


def sanitize_string(value: str) -> str:
    cleaned = _JWT_RE.sub("[redacted-token]", value)
    cleaned = _EMAIL_RE.sub("[redacted-email]", cleaned)
    cleaned = _URL_RE.sub("[redacted-url]", cleaned)
    cleaned = _PHONE_RE.sub("[redacted-phone]", cleaned)
    return cleaned[:MAX_STRING_LENGTH]


def sanitize_value(value):
    if isinstance(value, str):
        return sanitize_string(value)
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, nested in value.items():
            if isinstance(key, str) and key.lower() in SENSITIVE_KEYS:
                continue
            result[key] = sanitize_value(nested)
        return result
    return value


def sanitize_properties(properties: dict) -> dict:
    return sanitize_value(properties)
