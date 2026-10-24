"""Structured logging module with automatic secret redaction."""

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from blast_radius.config import get_settings

# Regex patterns for common sensitive values (AWS keys, tokens, private keys)
SENSITIVE_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.=]+"), "Bearer [REDACTED_TOKEN]"),
    (
        re.compile(r"-----BEGIN[ A-Z0-9_-]+KEY-----[\s\S]*?-----END[ A-Z0-9_-]+KEY-----"),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        re.compile(
            r"(?i)(password|secret|token|api_?key|access_?key)\s*[:=]\s*['\"]?([^'\"\s,]+)['\"]?"
        ),
        r"\1=[REDACTED]",
    ),
]


def redact_string(val: str, sensitive_keys: list[str] | None = None) -> str:
    """Redact sensitive patterns from a string."""
    result = val
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)

    if sensitive_keys:
        for key in sensitive_keys:
            # Pattern matching key: value or "key": "value"
            regex = re.compile(
                rf'(?i)(["\']?{re.escape(key)}["\']?\s*[:=]\s*["\']?)([^"\'\s,}}]+)(["\']?)'
            )
            result = regex.sub(r"\1[REDACTED]\3", result)
    return result


def redact_data(data: Any, sensitive_keys: list[str] | None = None) -> Any:
    """Recursively redact dictionary and list data structures."""
    if sensitive_keys is None:
        settings = get_settings()
        sensitive_keys = settings.redact_keys

    sensitive_keys_lower = {k.lower() for k in sensitive_keys}

    if isinstance(data, dict):
        cleaned: dict[str, Any] = {}
        for k, v in data.items():
            k_str = str(k).lower()
            if isinstance(v, (dict, list)):
                cleaned[k] = redact_data(v, sensitive_keys)
            elif any(s in k_str for s in sensitive_keys_lower):
                cleaned[k] = "[REDACTED]"
            else:
                cleaned[k] = redact_data(v, sensitive_keys)
        return cleaned
    elif isinstance(data, list):
        return [redact_data(item, sensitive_keys) for item in data]
    elif isinstance(data, tuple):
        return tuple(redact_data(item, sensitive_keys) for item in data)
    elif isinstance(data, str):
        return redact_string(data, sensitive_keys)
    return data


class RedactingJsonFormatter(logging.Formatter):
    """Custom log formatter that outputs redacted JSON."""

    def __init__(self, sensitive_keys: list[str] | None = None):
        super().__init__()
        self.sensitive_keys = sensitive_keys or get_settings().redact_keys

    def format(self, record: logging.LogRecord) -> str:
        raw_msg = record.getMessage()
        clean_msg = redact_string(raw_msg, self.sensitive_keys)

        log_payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": clean_msg,
            "module": record.module,
            "line": record.lineno,
        }

        # Include extra fields if provided
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            log_payload["extra"] = redact_data(record.extra, self.sensitive_keys)

        if record.exc_info:
            log_payload["exception"] = redact_string(self.formatException(record.exc_info))

        return json.dumps(log_payload)


class RedactingStandardFormatter(logging.Formatter):
    """Custom log formatter for standard human-readable logs with redaction."""

    def __init__(self, fmt: str | None = None, sensitive_keys: list[str] | None = None):
        standard_fmt = fmt or "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        super().__init__(standard_fmt)
        self.sensitive_keys = sensitive_keys or get_settings().redact_keys

    def format(self, record: logging.LogRecord) -> str:
        record.msg = redact_string(str(record.msg), self.sensitive_keys)
        if record.args:
            record.args = redact_data(record.args, self.sensitive_keys)
        return super().format(record)


def setup_logging() -> logging.Logger:
    """Configure root logger with chosen formatting and secret redaction."""
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers to prevent duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    if settings.log_json:
        console_handler.setFormatter(RedactingJsonFormatter(settings.redact_keys))
    else:
        console_handler.setFormatter(
            RedactingStandardFormatter(sensitive_keys=settings.redact_keys)
        )

    root_logger.addHandler(console_handler)
    return logging.getLogger("blast_radius")
