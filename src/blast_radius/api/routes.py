"""API route handlers for plan analysis and report exports."""

from typing import Any, Literal

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import PlainTextResponse

from blast_radius.config import get_settings
from blast_radius.models.report import FullAnalysisReport
from blast_radius.pipeline import BlastRadiusPipeline
from blast_radius.reporting.json_reporter import JsonReporter
from blast_radius.reporting.markdown_reporter import MarkdownReporter

router = APIRouter(prefix="/api/v1", tags=["Analysis"])
pipeline = BlastRadiusPipeline()


@router.post(
    "/analyze",
    response_model=FullAnalysisReport,
    summary="Analyze Terraform plan JSON",
    description="Evaluates Terraform plan JSON, calculates blast radius, and returns findings.",
)
async def analyze_plan(
    request: Request,
    file: UploadFile | None = File(None, description="Terraform plan JSON file upload"),
    critical_resources: list[str] = Query(
        default=[], description="List of resource addresses designated as critical"
    ),
) -> FullAnalysisReport:
    """Analyze Terraform plan JSON uploaded as multipart file or raw JSON body."""
    settings = get_settings()

    if file is not None:
        content = await file.read()
    else:
        content = await request.body()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No plan payload provided. Upload a file or pass JSON body.",
        )

    if len(content) > settings.max_plan_size_bytes:
        msg = (
            f"Plan payload ({len(content)} bytes) exceeds limit of {settings.max_plan_size_bytes}."
        )
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=msg,
        )

    crit_set = set(critical_resources) if critical_resources else None
    report = pipeline.run_analysis(content, critical_resources=crit_set)
    return report


@router.post(
    "/analyze/export",
    summary="Export analysis report as Markdown or JSON",
    description="Executes analysis and exports report as formatted Markdown or JSON.",
)
async def export_report(
    request: Request,
    format: Literal["markdown", "json"] = Query("markdown", description="Desired export format"),
    file: UploadFile | None = File(None),
) -> Any:
    """Export analysis result in Markdown or JSON format."""
    settings = get_settings()

    if file is not None:
        content = await file.read()
    else:
        content = await request.body()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No plan payload provided.",
        )

    if len(content) > settings.max_plan_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Plan payload exceeds maximum limit of {settings.max_plan_size_bytes} bytes.",
        )

    report = pipeline.run_analysis(content)

    if format == "json":
        return JsonReporter.generate_dict(report)

    markdown_text = MarkdownReporter.generate_markdown(report)
    return PlainTextResponse(content=markdown_text, media_type="text/markdown")
