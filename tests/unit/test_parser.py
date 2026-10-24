"""Unit tests for Module B: Terraform plan parser and change normalizer."""

from pathlib import Path

from blast_radius.models.plan import NormalizedAction
from blast_radius.parser.terraform import TerraformPlanParser

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def test_parse_add_resource():
    """Verify resource creation is parsed and normalized to CREATE."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "add_resource.json").read_bytes()
    plan = parser.parse_raw(content)

    assert plan.is_valid is True
    assert plan.raw_resource_count == 1
    assert plan.action_counts == {"create": 1}
    assert len(plan.destructive_changes) == 0

    change = plan.resource_changes[0]
    assert change.address == "aws_s3_bucket.logs"
    assert change.resource_type == "aws_s3_bucket"
    assert change.normalized_action == NormalizedAction.CREATE
    assert change.is_destructive is False


def test_parse_update_resource():
    """Verify resource modification is parsed and normalized to UPDATE."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "update_resource.json").read_bytes()
    plan = parser.parse_raw(content)

    assert plan.is_valid is True
    assert plan.raw_resource_count == 1
    assert plan.action_counts == {"update": 1}
    assert len(plan.destructive_changes) == 0

    change = plan.resource_changes[0]
    assert change.address == "aws_security_group_rule.allow_tls"
    assert change.normalized_action == NormalizedAction.UPDATE
    assert change.is_destructive is False


def test_parse_delete_isolated():
    """Verify deletion is parsed and flagged as destructive."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "delete_isolated.json").read_bytes()
    plan = parser.parse_raw(content)

    assert plan.is_valid is True
    assert plan.raw_resource_count == 1
    assert plan.action_counts == {"delete": 1}
    assert len(plan.destructive_changes) == 1

    change = plan.resource_changes[0]
    assert change.address == "aws_cloudwatch_log_group.dev_debug"
    assert change.normalized_action == NormalizedAction.DELETE
    assert change.is_destructive is True


def test_parse_delete_with_dependents():
    """Verify deletion with dependent resources and config references extraction."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "delete_with_dependents.json").read_bytes()
    plan = parser.parse_raw(content)

    assert plan.is_valid is True
    assert plan.raw_resource_count == 3
    assert plan.action_counts == {"delete": 1, "no-op": 2}
    assert len(plan.destructive_changes) == 1

    # Check that dependents extracted declared dependency on primary db
    by_addr = {rc.address: rc for rc in plan.resource_changes}
    assert "aws_db_instance.primary" in by_addr["aws_ecs_service.api"].declared_dependencies
    assert "aws_db_instance.primary" in by_addr["aws_route53_record.db"].declared_dependencies


def test_parse_replace_with_dependents():
    """Verify replacement action and replace_paths extraction."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "replace_with_dependents.json").read_bytes()
    plan = parser.parse_raw(content)

    assert plan.is_valid is True
    assert plan.raw_resource_count == 2
    assert plan.action_counts == {"replace": 1, "no-op": 1}
    assert len(plan.destructive_changes) == 1

    subnet_change = plan.resource_changes[0]
    assert subnet_change.normalized_action == NormalizedAction.REPLACE
    assert subnet_change.is_destructive is True
    assert "cidr_block" in subnet_change.replace_paths

    instance_change = plan.resource_changes[1]
    assert "aws_subnet.private_app" in instance_change.declared_dependencies


def test_parse_cyclic_dependency():
    """Verify cyclic configurations are parsed safely without infinite loops."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "cyclic_dependency.json").read_bytes()
    plan = parser.parse_raw(content)

    assert plan.is_valid is True
    assert plan.raw_resource_count == 2
    by_addr = {rc.address: rc for rc in plan.resource_changes}
    assert "aws_security_group.sg_b" in by_addr["aws_security_group.sg_a"].declared_dependencies
    assert "aws_security_group.sg_a" in by_addr["aws_security_group.sg_b"].declared_dependencies


def test_parse_sensitive_values_redaction():
    """Verify sensitive values in before/after attributes are redacted during parsing."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "sensitive_values.json").read_bytes()
    plan = parser.parse_raw(content)

    assert plan.is_valid is True
    db_change = plan.resource_changes[0]

    # Verify no plain text passwords or tokens survived
    assert db_change.before_attributes["master_password"] == "[REDACTED]"
    assert db_change.before_attributes["api_token"] == "[REDACTED]"
    assert db_change.after_attributes["master_password"] == "[REDACTED]"
    assert db_change.after_attributes["api_token"] == "[REDACTED]"
    # Non-sensitive attributes remain visible
    assert db_change.before_attributes["identifier"] == "prod-db"


def test_parse_unsupported_action():
    """Verify unrecognized action combination is flagged as UNSUPPORTED."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "unsupported_action.json").read_bytes()
    plan = parser.parse_raw(content)

    assert plan.is_valid is True
    change = plan.resource_changes[0]
    assert change.normalized_action == NormalizedAction.UNSUPPORTED
    assert any("unsupported action" in w.lower() for w in plan.warnings)


def test_parse_malformed_input():
    """Verify parser returns invalid plan on malformed JSON payload."""
    parser = TerraformPlanParser()
    content = (FIXTURES_DIR / "malformed.json").read_bytes()
    plan = parser.parse_raw(content)

    assert plan.is_valid is False
    assert plan.raw_resource_count == 0
    assert len(plan.warnings) > 0
