"""Unit tests for configuration management."""

from blast_radius.config import Settings, get_settings


def test_default_settings():
    """Verify default configuration values."""
    settings = Settings()
    assert settings.app_name == "Cloud Blast-Radius Simulator"
    assert settings.environment == "development"
    assert settings.debug is False
    assert settings.max_plan_size_bytes == 10 * 1024 * 1024
    assert "password" in settings.redact_keys
    assert "secret" in settings.redact_keys
    assert "token" in settings.redact_keys


def test_settings_override():
    """Verify settings can be overridden cleanly."""
    custom = Settings(
        environment="production",
        debug=True,
        max_plan_size_bytes=5 * 1024 * 1024,
    )
    assert custom.environment == "production"
    assert custom.debug is True
    assert custom.max_plan_size_bytes == 5 * 1024 * 1024


def test_get_settings_cached():
    """Verify get_settings returns a valid singleton instance."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
