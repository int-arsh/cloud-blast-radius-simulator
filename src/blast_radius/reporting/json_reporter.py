"""Module G: Structured JSON report generator."""

import json

from blast_radius.logging import redact_data
from blast_radius.models.report import FullAnalysisReport


class JsonReporter:
    """Generates structured JSON reports for automation and CI/CD ingestion."""

    @staticmethod
    def generate_dict(report: FullAnalysisReport) -> dict:
        """Convert FullAnalysisReport to dictionary with secret redaction guarantee."""
        raw_dict = report.model_dump()
        return redact_data(raw_dict)

    @classmethod
    def generate_json(cls, report: FullAnalysisReport, indent: int = 2) -> str:
        """Serialize FullAnalysisReport to pretty-printed JSON string."""
        clean_dict = cls.generate_dict(report)
        return json.dumps(clean_dict, indent=indent, default=str)
