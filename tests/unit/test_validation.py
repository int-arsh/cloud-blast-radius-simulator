"""Unit tests for Module A: Input validation."""

from pathlib import Path

from blast_radius.validation.validator import PlanValidator

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_validate_empty_content():
    """Verify empty payload is rejected with clear error."""
    validator = PlanValidator()
    result = validator.validate_raw(b"")
    assert result.is_valid is False
    assert any("empty" in err.lower() for err in result.errors)


def test_validate_oversized_payload():
    """Verify payloads exceeding max size limit are rejected safely."""
    validator = PlanValidator(max_size_bytes=100)
    oversized = b"a" * 200
    result = validator.validate_raw(oversized)
    assert result.is_valid is False
    assert any("exceeds configured limit" in err for err in result.errors)
    assert result.size_bytes == 200


def test_validate_malformed_json():
    """Verify malformed JSON syntax is caught with decode error."""
    validator = PlanValidator()
    malformed_path = FIXTURES_DIR / "malformed.json"
    result = validator.validate_raw(malformed_path.read_bytes())
    assert result.is_valid is False
    assert any("malformed json" in err.lower() for err in result.errors)


def test_validate_non_dict_json():
    """Verify non-dictionary top-level JSON is rejected."""
    validator = PlanValidator()
    result = validator.validate_raw(b'["item1", "item2"]')
    assert result.is_valid is False
    assert any("dictionary" in err.lower() for err in result.errors)


def test_validate_missing_format_version():
    """Verify missing format_version is flagged as an error."""
    validator = PlanValidator()
    result = validator.validate_raw(b'{"resource_changes": []}')
    assert result.is_valid is False
    assert any("format_version" in err for err in result.errors)


def test_validate_missing_resource_changes():
    """Verify missing resource_changes block is flagged as an error."""
    validator = PlanValidator()
    result = validator.validate_raw(b'{"format_version": "1.0"}')
    assert result.is_valid is False
    assert any("resource_changes" in err for err in result.errors)


def test_validate_unsupported_version_warning():
    """Verify unsupported major format version generates a warning but passes structurally."""
    validator = PlanValidator()
    fixture = FIXTURES_DIR / "unsupported_version.json"
    result = validator.validate_raw(fixture.read_bytes())
    assert result.is_valid is True
    assert any("outside verified range" in warn for warn in result.warnings)
    assert result.format_version == "99.0"
