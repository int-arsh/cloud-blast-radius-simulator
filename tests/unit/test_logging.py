"""Unit tests for structured logging and secret redaction."""

import json
import logging

from blast_radius.logging import RedactingJsonFormatter, redact_data, redact_string


def test_redact_aws_key_in_string():
    """Verify AWS access key IDs are masked in strings."""
    raw = "Deploying to AWS using AKIAIOSFODNN7EXAMPLE credentials"
    redacted = redact_string(raw)
    assert "AKIAIOSFODNN7EXAMPLE" not in redacted
    assert "[REDACTED_AWS_KEY]" in redacted


def test_redact_bearer_token():
    """Verify bearer tokens are masked."""
    raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz123"
    redacted = redact_string(raw)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in redacted
    assert "Bearer [REDACTED_TOKEN]" in redacted


def test_redact_private_key():
    """Verify PEM private keys are masked."""
    raw = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0\n-----END RSA PRIVATE KEY-----"
    redacted = redact_string(raw)
    assert "MIIEowIBAAKCAQEA0" not in redacted
    assert "[REDACTED_PRIVATE_KEY]" in redacted


def test_redact_dictionary_recursive():
    """Verify recursive dictionary masking for sensitive keys."""
    payload = {
        "resource": "aws_db_instance.primary",
        "db_password": "supersecretpassword123",
        "nested": {
            "api_token": "tok_live_998877",
            "safe_attribute": "db.t3.medium",
            "more_secrets": {
                "master_user_password": "AnotherSecretPassword!",
            },
        },
        "tags": ["env:prod", "managed:terraform"],
    }

    redacted = redact_data(payload)
    assert redacted["db_password"] == "[REDACTED]"
    assert redacted["nested"]["api_token"] == "[REDACTED]"
    assert redacted["nested"]["more_secrets"]["master_user_password"] == "[REDACTED]"
    assert redacted["nested"]["safe_attribute"] == "db.t3.medium"
    assert redacted["resource"] == "aws_db_instance.primary"
    assert redacted["tags"] == ["env:prod", "managed:terraform"]


def test_redacting_json_formatter():
    """Verify RedactingJsonFormatter outputs valid JSON and masks sensitive fields."""
    formatter = RedactingJsonFormatter(sensitive_keys=["token", "password"])
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="User authenticated with token=xyz789 secret password",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test_logger"
    assert "xyz789" not in parsed["message"]
    assert "token=[REDACTED]" in parsed["message"]
