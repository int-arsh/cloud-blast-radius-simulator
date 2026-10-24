"""Safe read-only live cloud inspection and state enrichment client.

Connects to AWS APIs using strictly read-only primitives (Describe*, Get*, List*, Head*)
to verify resource existence, active protection flags, out-of-band configuration drift,
and environment tags. Gracefully degrades to offline mode if unauthenticated.
"""

from __future__ import annotations

import logging
from typing import Any

from blast_radius.models.cloud import CloudEnrichmentReport, LiveResourceState
from blast_radius.models.plan import ParsedPlan, ResourceChange

logger = logging.getLogger(__name__)

# Permitted read-only API method prefixes
READ_ONLY_PREFIXES = ("describe_", "get_", "list_", "head_")


class ReadOnlySecurityViolation(Exception):
    """Raised when an unapproved mutating cloud API call is attempted."""


class CloudEnricher:
    """Read-only cloud state enricher for Terraform plan changes."""

    def __init__(
        self,
        profile: str | None = None,
        region: str | None = None,
        offline: bool = False,
        mock_states: dict[str, LiveResourceState] | None = None,
    ) -> None:
        self.profile = profile
        self.region = region or "us-east-1"
        self.offline = offline
        self.mock_states = mock_states or {}
        self.authenticated = False
        self.account_id: str | None = None
        self._session: Any = None

        if not self.offline:
            self._init_aws_session()

    def _init_aws_session(self) -> None:
        """Safely initialize AWS boto3 session and verify credentials via STS."""
        try:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError

            session_kwargs: dict[str, Any] = {"region_name": self.region}
            if self.profile:
                session_kwargs["profile_name"] = self.profile

            self._session = boto3.Session(**session_kwargs)
            sts = self._session.client("sts")

            # Validate that only read-only STS method is invoked
            self._verify_read_only_method("get_caller_identity")
            caller = sts.get_caller_identity()
            self.account_id = caller.get("Account")
            self.authenticated = True
            logger.info(
                "Authenticated with AWS account %s (region: %s)",
                self.account_id,
                self.region,
            )
        except (ImportError, BotoCoreError, ClientError, Exception) as err:
            logger.warning(
                "AWS credentials unavailable or unauthenticated (%s). "
                "Operating in safe offline simulation mode.",
                err,
            )
            self.authenticated = False

    @staticmethod
    def _verify_read_only_method(method_name: str) -> None:
        """Enforce strict read-only safety policy. Mutating APIs raise immediately."""
        method_lower = method_name.lower()
        if not any(method_lower.startswith(prefix) for prefix in READ_ONLY_PREFIXES):
            msg = (
                f"STRICT SECURITY PROHIBITION: Cloud mutation call '{method_name}' "
                f"is strictly prohibited. Only read-only operations are permitted."
            )
            raise ReadOnlySecurityViolation(msg)

    def enrich_plan(self, plan: ParsedPlan) -> CloudEnrichmentReport:
        """Correlate all planned resource changes against live cloud state."""
        report = CloudEnrichmentReport(
            provider="aws",
            authenticated=self.authenticated,
            region=self.region,
            profile=self.profile,
        )

        for rc in plan.resource_changes:
            report.resources_checked += 1
            state = self._inspect_resource(rc)
            report.resource_states[rc.address] = state

            if state.exists_in_cloud is True:
                report.resources_existing += 1
            elif state.exists_in_cloud is False:
                report.resources_missing += 1

            if state.drift_detected:
                report.drift_count += 1

            # Check protection safeguards on destructive actions
            if rc.is_destructive:
                if state.protection_flags.get("deletion_protection"):
                    warning = (
                        f"Active Safeguard: '{rc.address}' has DeletionProtection=True "
                        f"in live cloud; terraform destroy/replace will be rejected by AWS."
                    )
                    report.protection_warnings.append(warning)
                if state.protection_flags.get("termination_protection"):
                    warning = (
                        f"Active Safeguard: '{rc.address}' has DisableApiTermination=True "
                        f"in live cloud; EC2 instance termination will be rejected by AWS."
                    )
                    report.protection_warnings.append(warning)

            # Check production tags against destructive plans
            if state.is_production_flagged and rc.is_destructive:
                env_tag = state.tags.get("Environment", "prod")
                violation = (
                    f"Production Safeguard: Live resource '{rc.address}' is tagged as "
                    f"PRODUCTION ({env_tag}) and slated for {rc.normalized_action}."
                )
                report.production_violations.append(violation)

        return report

    def _inspect_resource(self, rc: ResourceChange) -> LiveResourceState:
        """Inspect a single resource change, honoring injected mocks or live API."""
        # Check mock registry first (for testing or offline simulation)
        if rc.address in self.mock_states:
            return self.mock_states[rc.address]

        if not self.authenticated or not self._session:
            return LiveResourceState(
                address=rc.address,
                resource_type=rc.resource_type,
                resource_id=None,
                exists_in_cloud=None,
                provenance="offline_unauthenticated",
            )

        # Dispatch based on resource type
        if rc.resource_type == "aws_db_instance":
            return self._inspect_rds(rc)
        if rc.resource_type == "aws_instance":
            return self._inspect_ec2(rc)
        if rc.resource_type == "aws_s3_bucket":
            return self._inspect_s3(rc)

        return self._inspect_generic(rc)

    def _inspect_rds(self, rc: ResourceChange) -> LiveResourceState:
        """Inspect AWS RDS DB instance via describe_db_instances."""
        db_id = (
            rc.before_attributes.get("identifier")
            or rc.after_attributes.get("identifier")
            or rc.resource_name
        )
        try:
            rds = self._session.client("rds")
            self._verify_read_only_method("describe_db_instances")
            resp = rds.describe_db_instances(DBInstanceIdentifier=db_id)
            instances = resp.get("DBInstances", [])
            if not instances:
                return LiveResourceState(
                    address=rc.address,
                    resource_type=rc.resource_type,
                    resource_id=db_id,
                    exists_in_cloud=False,
                    provenance="aws_api(rds.describe_db_instances)",
                )

            inst = instances[0]
            del_prot = bool(inst.get("DeletionProtection", False))
            tags = {t["Key"]: t["Value"] for t in inst.get("TagList", [])}

            # Compare drift between planned before and live cloud
            drift_messages = []
            live_storage = inst.get("AllocatedStorage")
            before_storage = rc.before_attributes.get("allocated_storage")
            if (
                before_storage is not None
                and live_storage is not None
                and before_storage != live_storage
            ):
                drift_messages.append(
                    f"AllocatedStorage drift: plan expects {before_storage} GB, "
                    f"live cloud has {live_storage} GB"
                )

            is_prod = any(
                tags.get(k, "").lower() in ("prod", "production")
                for k in ("Environment", "Env", "Stage")
            )

            return LiveResourceState(
                address=rc.address,
                resource_type=rc.resource_type,
                resource_id=db_id,
                exists_in_cloud=True,
                tags=tags,
                protection_flags={"deletion_protection": del_prot},
                live_attributes={
                    "allocated_storage": live_storage,
                    "engine": inst.get("Engine"),
                    "status": inst.get("DBInstanceStatus"),
                },
                drift_detected=len(drift_messages) > 0,
                drift_messages=drift_messages,
                is_production_flagged=is_prod,
                provenance="aws_api(rds.describe_db_instances)",
            )
        except Exception as err:
            logger.debug("RDS inspection failed for %s: %s", db_id, err)
            return LiveResourceState(
                address=rc.address,
                resource_type=rc.resource_type,
                resource_id=db_id,
                exists_in_cloud=None,
                provenance=f"aws_api_error({type(err).__name__})",
            )

    def _inspect_ec2(self, rc: ResourceChange) -> LiveResourceState:
        """Inspect AWS EC2 instance via describe_instances."""
        instance_id = rc.before_attributes.get("id") or rc.after_attributes.get("id")
        if not instance_id:
            return LiveResourceState(
                address=rc.address,
                resource_type=rc.resource_type,
                exists_in_cloud=None,
                provenance="aws_api(missing_instance_id)",
            )
        try:
            ec2 = self._session.client("ec2")
            self._verify_read_only_method("describe_instances")
            resp = ec2.describe_instances(InstanceIds=[instance_id])
            reservations = resp.get("Reservations", [])
            if not reservations or not reservations[0].get("Instances"):
                return LiveResourceState(
                    address=rc.address,
                    resource_type=rc.resource_type,
                    resource_id=instance_id,
                    exists_in_cloud=False,
                    provenance="aws_api(ec2.describe_instances)",
                )

            inst = reservations[0]["Instances"][0]
            tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}

            # Check termination protection
            term_prot = False
            try:
                self._verify_read_only_method("describe_instance_attribute")
                attr_resp = ec2.describe_instance_attribute(
                    InstanceId=instance_id, Attribute="disableApiTermination"
                )
                term_prot = bool(attr_resp.get("DisableApiTermination", {}).get("Value", False))
            except Exception:
                pass

            is_prod = any(
                tags.get(k, "").lower() in ("prod", "production")
                for k in ("Environment", "Env", "Stage")
            )

            return LiveResourceState(
                address=rc.address,
                resource_type=rc.resource_type,
                resource_id=instance_id,
                exists_in_cloud=True,
                tags=tags,
                protection_flags={"termination_protection": term_prot},
                live_attributes={
                    "state": inst.get("State", {}).get("Name"),
                    "instance_type": inst.get("InstanceType"),
                },
                drift_detected=False,
                is_production_flagged=is_prod,
                provenance="aws_api(ec2.describe_instances)",
            )
        except Exception as err:
            logger.debug("EC2 inspection failed for %s: %s", instance_id, err)
            return LiveResourceState(
                address=rc.address,
                resource_type=rc.resource_type,
                resource_id=instance_id,
                exists_in_cloud=None,
                provenance=f"aws_api_error({type(err).__name__})",
            )

    def _inspect_s3(self, rc: ResourceChange) -> LiveResourceState:
        """Inspect AWS S3 bucket via head_bucket and get_bucket_tagging."""
        bucket_name = (
            rc.before_attributes.get("bucket")
            or rc.after_attributes.get("bucket")
            or rc.resource_name
        )
        try:
            s3 = self._session.client("s3")
            self._verify_read_only_method("head_bucket")
            s3.head_bucket(Bucket=bucket_name)

            tags: dict[str, str] = {}
            try:
                self._verify_read_only_method("get_bucket_tagging")
                tag_resp = s3.get_bucket_tagging(Bucket=bucket_name)
                tags = {t["Key"]: t["Value"] for t in tag_resp.get("TagSet", [])}
            except Exception:
                pass

            is_prod = any(
                tags.get(k, "").lower() in ("prod", "production")
                for k in ("Environment", "Env", "Stage")
            )

            return LiveResourceState(
                address=rc.address,
                resource_type=rc.resource_type,
                resource_id=bucket_name,
                exists_in_cloud=True,
                tags=tags,
                protection_flags={},
                drift_detected=False,
                is_production_flagged=is_prod,
                provenance="aws_api(s3.head_bucket)",
            )
        except Exception as err:
            logger.debug("S3 inspection failed for %s: %s", bucket_name, err)
            return LiveResourceState(
                address=rc.address,
                resource_type=rc.resource_type,
                resource_id=bucket_name,
                exists_in_cloud=False,
                provenance=f"aws_api_error({type(err).__name__})",
            )

    def _inspect_generic(self, rc: ResourceChange) -> LiveResourceState:
        """Fallback inspection for resource types without specialized inspectors."""
        return LiveResourceState(
            address=rc.address,
            resource_type=rc.resource_type,
            resource_id=rc.resource_name,
            exists_in_cloud=None,
            provenance="aws_api(generic_unsupported)",
        )
