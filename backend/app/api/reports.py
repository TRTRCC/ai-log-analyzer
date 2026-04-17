"""
Report API Routes
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db_session
from app.models import Report, ReportType, AnalysisTask
from app.api.auth import get_current_user, get_admin_user
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


# Request/Response models
class ReportResponse(BaseModel):
    id: str
    task_id: Optional[str] = None
    user_id: str
    report_type: str
    report_date: Optional[date] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    file_path: Optional[str] = None
    created_at: datetime


class ReportContent(BaseModel):
    title: str
    summary: str
    sections: Dict[str, Any]


class ReportListResponse(BaseModel):
    reports: List[ReportResponse]
    total: int


# Routes
@router.get("/", response_model=ReportListResponse)
async def list_reports(
    report_type: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """List reports"""

    query = select(Report)

    # Filter by ownership for non-admin
    if current_user["role"] not in ["super_admin", "audit_admin"]:
        query = query.where(Report.user_id == UUID(current_user["id"]))

    if report_type:
        query = query.where(Report.report_type == report_type)
    if start_date:
        query = query.where(Report.report_date >= start_date)
    if end_date:
        query = query.where(Report.report_date <= end_date)

    query = query.order_by(Report.created_at.desc())
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    reports = result.scalars().all()

    return ReportListResponse(
        reports=[
            ReportResponse(
                id=str(r.id),
                task_id=str(r.task_id) if r.task_id else None,
                user_id=str(r.user_id),
                report_type=r.report_type,
                report_date=r.report_date,
                title=r.title,
                summary=r.summary,
                file_path=r.file_path,
                created_at=r.created_at
            )
            for r in reports
        ],
        total=len(reports) + offset
    )


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get report details"""

    result = await db.execute(
        select(Report).where(Report.id == UUID(report_id))
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Check access
    if str(report.user_id) != current_user["id"] and \
       current_user["role"] not in ["super_admin", "audit_admin"]:
        raise HTTPException(status_code=403, detail="Access denied")

    return ReportResponse(
        id=str(report.id),
        task_id=str(report.task_id) if report.task_id else None,
        user_id=str(report.user_id),
        report_type=report.report_type,
        report_date=report.report_date,
        title=report.title,
        summary=report.summary,
        file_path=report.file_path,
        created_at=report.created_at
    )


@router.get("/{report_id}/content")
async def get_report_content(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get full report content"""

    result = await db.execute(
        select(Report).where(Report.id == UUID(report_id))
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Check access
    if str(report.user_id) != current_user["id"] and \
       current_user["role"] not in ["super_admin", "audit_admin"]:
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "id": str(report.id),
        "title": report.title,
        "content": report.content,
        "summary": report.summary
    }


@router.get("/{report_id}/download")
async def download_report(
    report_id: str,
    format: str = Query(default="pdf"),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Download report file"""

    result = await db.execute(
        select(Report).where(Report.id == UUID(report_id))
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Check access
    if str(report.user_id) != current_user["id"] and \
       current_user["role"] not in ["super_admin", "audit_admin"]:
        raise HTTPException(status_code=403, detail="Access denied")

    # Return download URL or file content
    return {
        "report_id": str(report.id),
        "file_path": report.file_path,
        "format": format,
        "download_url": f"/api/v1/reports/{report_id}/file/{format}"
    }


@router.get("/{report_id}/file/{format}")
async def get_report_file(
    report_id: str,
    format: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get report file content"""

    # This would return actual file in production
    from fastapi.responses import Response

    result = await db.execute(
        select(Report).where(Report.id == UUID(report_id))
    )
    report = result.scalar_one_or_none()

    if not report or not report.file_path:
        raise HTTPException(status_code=404, detail="Report file not found")

    # Mock file content
    content = generate_report_content(report)

    if format == "pdf":
        # Would generate PDF in production
        return Response(
            content=content.encode(),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={report.title}.pdf"}
        )
    elif format == "html":
        return Response(
            content=content.encode(),
            media_type="text/html"
        )
    elif format == "markdown":
        return Response(
            content=content.encode(),
            media_type="text/markdown"
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid format")


@router.post("/generate")
async def generate_manual_report(
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Generate new manual report"""

    # Create report task
    report = Report(
        user_id=UUID(current_user["id"]),
        report_type=ReportType.ADHOC,
        report_date=date.today(),
        title=f"Manual Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        summary="Generating..."
    )

    db.add(report)
    await db.commit()
    await db.refresh(report)

    # Start generation in background
    background_tasks.add_task(generate_report_background, str(report.id))

    return {"report_id": str(report.id), "status": "generating"}


@router.delete("/{report_id}")
async def delete_report(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Delete report"""

    result = await db.execute(
        select(Report).where(Report.id == UUID(report_id))
    )
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Only owner or admin can delete
    if str(report.user_id) != current_user["id"] and \
       current_user["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Access denied")

    await db.delete(report)
    await db.commit()

    return {"message": "Report deleted"}


# Helper functions
def generate_report_content(report: Report) -> str:
    """Generate report content (mock)"""

    return f"""
# {report.title or 'Analysis Report'}

## Summary
{report.summary or 'No summary available'}

## Generated
{report.created_at.strftime('%Y-%m-%d %H:%M:%S')}

---

This is a placeholder report content. In production, this would contain:
- Log statistics
- Anomaly analysis
- Security findings
- Performance metrics
- AI recommendations
"""


async def generate_report_background(report_id: str):
    """Background task to generate report"""

    from app.database import async_session_factory

    async with async_session_factory() as db:
        try:
            result = await db.execute(
                select(Report).where(Report.id == UUID(report_id))
            )
            report = result.scalar_one()

            # Generate content
            content = {
                "summary": "Daily analysis report",
                "statistics": {
                    "total_logs": 100000,
                    "errors": 500,
                    "warnings": 1000
                },
                "findings": [
                    {"title": "Network anomaly", "description": "Interface flapping detected"},
                    {"title": "Security event", "description": "Failed login attempts"}
                ],
                "recommendations": [
                    "Investigate switch connectivity",
                    "Review authentication policies"
                ]
            }

            report.content = content
            report.summary = "Report generated successfully"
            report.file_path = f"/data/reports/{report_id}.pdf"

            await db.commit()

            logger.info(f"Report {report_id} generated")

        except Exception as e:
            logger.error(f"Report generation failed: {e}")