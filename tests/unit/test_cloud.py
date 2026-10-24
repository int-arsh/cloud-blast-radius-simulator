"""Unit tests for Phase 9: Safe read-only live cloud inspection and state enrichment."""

import json
from unittest.mock import MagicMock, patch

import pytest

from blast_radius.cloud.client import (
    CloudEnricher,
    ReadOnlySecurityViolation,
)
from blast_radius.models.cloud import CloudEnrichmentReport, LiveResourceState
from blast_radius.models.plan import NormalizedAction, ParsedPlan, ResourceChange
from blast_radius.models.risk import DecisionStatus
from blast_radius.pipeline import BlastRadiusPipeline
from blast_radius.reporting.markdown_reporter import MarkdownReporter


def _create_mock_parsed_plan(
    resource_changes: list[ResourceChange],
) -> ParsedPlan:
    """Helper to assemble a minimal ParsedPlan."""
    return ParsedPlan(
        format_version="1.2",
        terraform_version="1.5.7",
        resource_changes=resource_changes,
        is_valid=True,
    )


class TestReadOnlyEnforcement:
    """Validate that mutating cloud calls are strictly blocked by safety guardrails."""

    def test_read_only_verification_allows_safe_prefixes(self) -> None:
        safe_methods = [
            "describe_db_instances",
            "describe_instances",
            "get_caller_identity",
            "get_bucket_tagging",
            "list_buckets",
            "head_bucket",
        ]
        for method in safe_methods:
            # Should not raise
            CloudEnricher._verify_read_only_method(method)

    def test_read_only_verification_blocks_mutations(self) -> None:
        unsafe_methods = [
            "delete_db_instance",
            "modify_db_instance",
            "terminate_instances",
            "stop_instances",
            "create_bucket",
            "put_bucket_policy",
            "delete_bucket",
            "update_service",
        ]
        for method in unsafe_methods:
            with pytest.raises(ReadOnlySecurityViolation) as exc_info:
                CloudEnricher._verify_read_only_method(method)
            assert "strictly prohibited" in str(exc_info.value)


class TestCloudEnricherOffline:
    """Validate offline simulation and graceful degradation without active credentials."""

    def test_enricher_offline_mode(self) -> None:
        enricher = CloudEnricher(offline=True)
        assert enricher.offline is True
        assert enricher.authenticated is False
        assert enricher.account_id is None

    def test_enricher_unauthenticated_inspection(self) -> None:
        enricher = CloudEnricher(offline=True)
        rc = ResourceChange(
            address="aws_db_instance.db",
            resource_type="aws_db_instance",
            resource_name="db",
            normalized_action=NormalizedAction.REPLACE,
            is_destructive=True,
            before_attributes={"identifier": "production-db"},
        )
        plan = _create_mock_parsed_plan([rc])
        report = enricher.enrich_plan(plan)

        assert report.authenticated is False
        assert report.resources_checked == 1
        assert "aws_db_instance.db" in report.resource_states
        state = report.resource_states["aws_db_instance.db"]
        assert state.provenance == "offline_unauthenticated"
        assert state.exists_in_cloud is None


class TestMockStateEnrichment:
    """Validate enrichment behavior using injected mock cloud states."""

    def test_mock_states_correlate_correctly(self) -> None:
        mock_state = LiveResourceState(
            address="aws_db_instance.db",
            resource_type="aws_db_instance",
            resource_id="prod-db-1",
            exists_in_cloud=True,
            tags={"Environment": "production", "Owner": "DataPlatform"},
            protection_flags={"deletion_protection": True},
            live_attributes={"allocated_storage": 100},
            drift_detected=True,
            drift_messages=["AllocatedStorage drift: plan expects 50 GB, live cloud has 100 GB"],
            is_production_flagged=True,
            provenance="offline_mock",
        )

        enricher = CloudEnricher(
            offline=True,
            mock_states={"aws_db_instance.db": mock_state},
        )

        rc = ResourceChange(
            address="aws_db_instance.db",
            resource_type="aws_db_instance",
            resource_name="db",
            normalized_action=NormalizedAction.DELETE,
            is_destructive=True,
            before_attributes={"identifier": "prod-db-1", "allocated_storage": 50},
        )
        plan = _create_mock_parsed_plan([rc])
        report = enricher.enrich_plan(plan)

        assert report.resources_checked == 1
        assert report.resources_existing == 1
        assert report.drift_count == 1
        assert len(report.protection_warnings) == 1
        assert "DeletionProtection=True" in report.protection_warnings[0]
        assert len(report.production_violations) == 1
        assert "PRODUCTION" in report.production_violations[0]


class TestLiveRDSInspection:
    """Validate RDS describe logic with mocked boto3 client."""

    @patch("boto3.Session")
    def test_rds_inspection_existing_with_drift_and_safeguards(self, mock_boto_session) -> None:
        mock_session_inst = MagicMock()
        mock_boto_session.return_value = mock_session_inst

        # Mock STS caller identity
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}
        # Mock RDS client
        mock_rds = MagicMock()
        mock_rds.describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "DBInstanceIdentifier": "primary-postgres",
                    "DeletionProtection": True,
                    "AllocatedStorage": 200,
                    "Engine": "postgres",
                    "DBInstanceStatus": "available",
                    "TagList": [{"Key": "Environment", "Value": "Production"}],
                }
            ]
        }

        mock_session_inst.client.side_effect = lambda svc: {
            "sts": mock_sts,
            "rds": mock_rds,
        }.get(svc, MagicMock())

        enricher = CloudEnricher(offline=False, region="us-east-1")
        assert enricher.authenticated is True
        assert enricher.account_id == "123456789012"

        rc = ResourceChange(
            address="aws_db_instance.main",
            resource_type="aws_db_instance",
            resource_name="main",
            normalized_action=NormalizedAction.REPLACE,
            is_destructive=True,
            before_attributes={"identifier": "primary-postgres", "allocated_storage": 100},
        )
        plan = _create_mock_parsed_plan([rc])
        report = enricher.enrich_plan(plan)

        assert report.resources_checked == 1
        assert report.resources_existing == 1
        assert report.drift_count == 1
        state = report.resource_states["aws_db_instance.main"]
        assert state.exists_in_cloud is True
        assert state.protection_flags["deletion_protection"] is True
        assert state.is_production_flagged is True
        assert len(state.drift_messages) == 1
        assert "plan expects 100 GB, live cloud has 200 GB" in state.drift_messages[0]


class TestLiveEC2Inspection:
    """Validate EC2 describe logic with termination protection checks."""

    @patch("boto3.Session")
    def test_ec2_inspection_with_termination_protection(self, mock_boto_session) -> None:
        mock_session_inst = MagicMock()
        mock_boto_session.return_value = mock_session_inst

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}

        mock_ec2 = MagicMock()
        mock_ec2.describe_instances.return_value = {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-0123456789abcdef0",
                            "State": {"Name": "running"},
                            "InstanceType": "m5.large",
                            "Tags": [{"Key": "Environment", "Value": "prod"}],
                        }
                    ]
                }
            ]
        }
        mock_ec2.describe_instance_attribute.return_value = {
            "DisableApiTermination": {"Value": True}
        }

        mock_session_inst.client.side_effect = lambda svc: {
            "sts": mock_sts,
            "ec2": mock_ec2,
        }.get(svc, MagicMock())

        enricher = CloudEnricher(offline=False)
        rc = ResourceChange(
            address="aws_instance.bastion",
            resource_type="aws_instance",
            resource_name="bastion",
            normalized_action=NormalizedAction.DELETE,
            is_destructive=True,
            before_attributes={"id": "i-0123456789abcdef0"},
        )
        plan = _create_mock_parsed_plan([rc])
        report = enricher.enrich_plan(plan)

        assert report.resources_existing == 1
        state = report.resource_states["aws_instance.bastion"]
        assert state.protection_flags["termination_protection"] is True
        assert state.is_production_flagged is True
        assert len(report.protection_warnings) == 1
        assert "DisableApiTermination=True" in report.protection_warnings[0]


class TestPipelineCloudEnrichmentIntegration:
    """Validate pipeline behavior when live cloud enricher is injected."""

    def test_pipeline_elevates_pass_to_review_required_on_active_safeguard(self) -> None:
        raw_plan = {
            "format_version": "1.2",
            "terraform_version": "1.5.7",
            "resource_changes": [
                {
                    "address": "aws_db_instance.db",
                    "type": "aws_db_instance",
                    "name": "db",
                    "change": {
                        "actions": ["delete"],
                        "before": {"identifier": "prod-db"},
                        "after": None,
                    },
                }
            ],
        }
        content = json.dumps(raw_plan).encode()

        mock_state = LiveResourceState(
            address="aws_db_instance.db",
            resource_type="aws_db_instance",
            resource_id="prod-db",
            exists_in_cloud=True,
            tags={"Environment": "production"},
            protection_flags={"deletion_protection": True},
            is_production_flagged=True,
            provenance="offline_mock",
        )
        enricher = CloudEnricher(
            offline=True,
            mock_states={"aws_db_instance.db": mock_state},
        )

        pipeline = BlastRadiusPipeline()
        report = pipeline.run_analysis(content, cloud_enricher=enricher)

        assert report.cloud_enrichment is not None
        assert report.cloud_enrichment.resources_existing == 1
        # Gate status must be elevated to REVIEW_REQUIRED or BLOCKED
        assert report.decision_status in (
            DecisionStatus.REVIEW_REQUIRED,
            DecisionStatus.BLOCKED,
        )
        assert any("DeletionProtection" in w for w in report.warnings)

    def test_markdown_report_renders_cloud_enrichment(self) -> None:
        enrichment = CloudEnrichmentReport(
            provider="aws",
            authenticated=True,
            region="us-east-1",
            profile="production2",
            resources_checked=5,
            resources_existing=5,
            resources_missing=0,
            protection_warnings=[
                "Active Safeguard: 'aws_db_instance.db' has DeletionProtection=True"
            ],
            production_violations=[
                "Production Safeguard: 'aws_db_instance.db' is tagged as PRODUCTION"
            ],
        )
        raw_plan = {
            "format_version": "1.2",
            "resource_changes": [
                {
                    "address": "aws_s3_bucket.data",
                    "type": "aws_s3_bucket",
                    "name": "data",
                    "change": {"actions": ["create"], "before": None, "after": {}},
                }
            ],
        }
        pipeline = BlastRadiusPipeline()
        report = pipeline.run_analysis(json.dumps(raw_plan).encode())
        # Attach enrichment manually to test markdown rendering
        report.cloud_enrichment = enrichment

        markdown = MarkdownReporter.generate_markdown(report)
        assert "## 6. Live Cloud State & Safeguards (Read-Only)" in markdown
        assert "AWS" in markdown
        assert "Active Protection Safeguards" in markdown
        assert "DeletionProtection=True" in markdown
        assert "Live Production Safeguard Violations" in markdown


class TestLiveS3AndGenericInspection:
    """Validate S3 bucket inspection and generic fallback logic."""

    @patch("boto3.Session")
    def test_s3_inspection_with_production_tags(self, mock_boto_session) -> None:
        mock_session_inst = MagicMock()
        mock_boto_session.return_value = mock_session_inst

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}

        mock_s3 = MagicMock()
        mock_s3.head_bucket.return_value = {}
        mock_s3.get_bucket_tagging.return_value = {
            "TagSet": [{"Key": "Environment", "Value": "Production"}]
        }

        mock_session_inst.client.side_effect = lambda svc: {
            "sts": mock_sts,
            "s3": mock_s3,
        }.get(svc, MagicMock())

        enricher = CloudEnricher(offline=False)
        rc = ResourceChange(
            address="aws_s3_bucket.media",
            resource_type="aws_s3_bucket",
            resource_name="media",
            normalized_action=NormalizedAction.DELETE,
            is_destructive=True,
            before_attributes={"bucket": "prod-media-assets"},
        )
        plan = _create_mock_parsed_plan([rc])
        report = enricher.enrich_plan(plan)

        assert report.resources_existing == 1
        state = report.resource_states["aws_s3_bucket.media"]
        assert state.exists_in_cloud is True
        assert state.is_production_flagged is True
        assert len(report.production_violations) == 1

    @patch("boto3.Session")
    def test_generic_resource_fallback(self, mock_boto_session) -> None:
        mock_session_inst = MagicMock()
        mock_boto_session.return_value = mock_session_inst
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}
        mock_session_inst.client.return_value = mock_sts

        enricher = CloudEnricher(offline=False)
        rc = ResourceChange(
            address="aws_sqs_queue.jobs",
            resource_type="aws_sqs_queue",
            resource_name="jobs",
            normalized_action=NormalizedAction.CREATE,
            is_destructive=False,
        )
        plan = _create_mock_parsed_plan([rc])
        report = enricher.enrich_plan(plan)

        state = report.resource_states["aws_sqs_queue.jobs"]
        assert state.provenance == "aws_api(generic_unsupported)"
