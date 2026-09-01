import re
import html
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Patterns for potential malicious code/script injection
SUSPICIOUS_PATTERNS = [
    r"<\s*script[^>]*>", r"javascript:", r"onload\s*=", r"onerror\s*=",
    r"SELECT\s+.*\s+FROM", r"DROP\s+TABLE", r"INSERT\s+INTO", r"DELETE\s+FROM",
    r"UNION\s+SELECT", r"OR\s+1\s*=\s*1", r"exec\s*\(", r"eval\s*\(",
    r"import\s+os", r"subprocess\.", r"__import__"
]

def sanitize_input(text: str, max_length: int = 2000) -> Tuple[bool, str]:
    """
    Sanitizes user/admin input text:
    - Protects against malicious injection patterns
    - Preserves supported Telegram custom animated emojis and HTML formatting (<tg-emoji>, <b>, <i>, <code>, <s>)
    
    Returns (is_safe: bool, sanitized_text: str)
    """
    if not text:
        return True, ""

    text_str = str(text).strip()[:max_length]

    # Check for malicious code/injection patterns
    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, text_str, re.IGNORECASE):
            logger.warning(f"Security Alert: Suspicious input pattern detected: {pattern}")
            return False, html.escape(text_str)

    return True, text_str

def format_4digit_id(service_id: str) -> str:
    """Format service ID to clean 4-digit display format (e.g. S_01 -> 0001, S_12 -> 0012)."""
    if not service_id:
        return "0000"
    digits = re.sub(r'\D', '', str(service_id))
    if digits:
        return f"{int(digits):04d}"
    # Fallback to uppercase 4-char string if no digits present
    return str(service_id).upper()[:4].zfill(4)

def is_valid_uuid(val: Any) -> bool:
    """Check if a value is a valid 36-character UUID string before querying PostgreSQL uuid columns."""
    if not val:
        return False
    v_str = str(val).strip()
    if len(v_str) != 36:
        return False
    import uuid
    try:
        u = uuid.UUID(v_str)
        return str(u) == v_str.lower()
    except Exception:
        return False
