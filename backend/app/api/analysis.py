"""
AI Analysis API Routes
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID
import json

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db_session
from app.models import AnalysisTask, TaskType, TaskStatus, LogType, AIProvider, AIModel, User
from app.api.auth import get_current_user
from app.services.auth import auth_service
from app.ai.engine import ai_engine, get_ai_engine
from app.services.log_parser import log_sampler
from app.utils.logging import get_logger
from app.utils.helpers import generate_uuid

logger = get_logger(__name__)

router = APIRouter()


# Request/Response models
class AnalysisTaskCreate(BaseModel):
    task_type: str = Field(default="manual_full")
    log_type: str = Field(default="all")
    time_range_start: Optional[datetime] = None
    time_range_end: Optional[datetime] = None
    devices: Optional[List[str]] = None
    model_id: Optional[str] = None
    provider_id: Optional[str] = None
    analysis_type: str = Field(default="general")


class AnalysisTaskResponse(BaseModel):
    id: str
    user_id: str
    task_type: str
    status: str
    log_type: str
    time_range_start: Optional[datetime] = None
    time_range_end: Optional[datetime] = None
    progress_percent: int
    model_id: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    result: Optional[Dict] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class AnalysisResultResponse(BaseModel):
    task_id: str
    success: bool
    summary: Optional[str] = None
    findings: Optional[List[Dict]] = None
    recommendations: Optional[List[str]] = None
    input_tokens: int
    output_tokens: int
    model_used: str
    duration_ms: int


class AIProviderResponse(BaseModel):
    id: str
    name: str
    display_name: Optional[str] = None
    provider_type: str
    is_active: bool
    is_default: bool


class AIModelResponse(BaseModel):
    id: str
    provider_id: str
    model_name: str
    display_name: Optional[str] = None
    max_tokens: Optional[int] = None
    is_active: bool
    is_default: bool


# Helper
def check_ai_permission(current_user: dict) -> bool:
    """Check if user can run AI analysis"""

    # All users can run manual analysis (with their log access)
    return True


async def get_logs_sample_for_analysis(
    time_start: Optional[datetime],
    time_end: Optional[datetime],
    log_type: str,
    devices: Optional[List[str]]
) -> str:
    """Get sample of logs for AI analysis"""

    # In production, query ClickHouse and use log_sampler
    # Mock sample for now

    sample_logs = """
[2024-04-17 08:00:15] [ERROR] [web-01] Connection timeout to database
[2024-04-17 08:00:20] [WARNING] [switch-01] Interface eth0 flapping
[2024-04-17 08:01:00] [INFO] [web-02] Request processed successfully
[2024-04-17 08:01:30] [ERROR] [db-01] Query execution time exceeded threshold
[2024-04-17 08:02:00] [WARNING] [k8s-master] Pod memory usage high
"""

    return sample_logs


# Routes
@router.post("/tasks", response_model=AnalysisTaskResponse)
async def create_analysis_task(
    request: AnalysisTaskCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Create new AI analysis task"""

    check_ai_permission(current_user)

    # Validate log type access
    user_role = current_user.get("role")
    if user_role not in ["super_admin", "audit_admin"]:
        type_map = {
            "network_user": "network",
            "server_user": "server",
            "k8s_user": "k8s"
        }
        request.log_type = type_map.get(user_role, request.log_type)

    # Create task
    task = AnalysisTask(
        user_id=UUID(current_user["id"]),
        task_type=request.task_type,
        status=TaskStatus.PENDING,
        log_type=request.log_type,
        time_range_start=request.time_range_start,
        time_range_end=request.time_range_end,
        devices=request.devices,
        model_id=UUID(request.model_id) if request.model_id else None,
        provider_id=UUID(request.provider_id) if request.provider_id else None,
    )

    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Start background analysis
    background_tasks.add_task(
        run_analysis_task,
        str(task.id),
        request.analysis_type,
        request.model_id,
        request.provider_id
    )

    logger.info(f"Analysis task created: {task.id}")

    return AnalysisTaskResponse(
        id=str(task.id),
        user_id=str(task.user_id),
        task_type=task.task_type,
        status=task.status,
        log_type=task.log_type,
        time_range_start=task.time_range_start,
        time_range_end=task.time_range_end,
        progress_percent=task.progress_percent,
        model_id=str(task.model_id) if task.model_id else None,
        input_tokens=task.input_tokens,
        output_tokens=task.output_tokens,
        result=task.result,
        error_message=task.error_message,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at
    )


@router.get("/tasks", response_model=List[AnalysisTaskResponse])
async def list_analysis_tasks(
    status: Optional[str] = Query(None),
    log_type: Optional[str] = Query(None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """List analysis tasks"""

    query = select(AnalysisTask).where(
        AnalysisTask.user_id == UUID(current_user["id"])
    )

    if status:
        query = query.where(AnalysisTask.status == status)
    if log_type:
        query = query.where(AnalysisTask.log_type == log_type)

    query = query.order_by(AnalysisTask.created_at.desc())
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    tasks = result.scalars().all()

    return [
        AnalysisTaskResponse(
            id=str(t.id),
            user_id=str(t.user_id),
            task_type=t.task_type,
            status=t.status,
            log_type=t.log_type,
            time_range_start=t.time_range_start,
            time_range_end=t.time_range_end,
            progress_percent=t.progress_percent,
            model_id=str(t.model_id) if t.model_id else None,
            input_tokens=t.input_tokens,
            output_tokens=t.output_tokens,
            result=t.result,
            error_message=t.error_message,
            created_at=t.created_at,
            started_at=t.started_at,
            completed_at=t.completed_at
        )
        for t in tasks
    ]


@router.get("/tasks/{task_id}", response_model=AnalysisTaskResponse)
async def get_analysis_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get analysis task details"""

    result = await db.execute(
        select(AnalysisTask).where(AnalysisTask.id == UUID(task_id))
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Check ownership or admin
    if str(task.user_id) != current_user["id"] and \
       current_user["role"] not in ["super_admin", "audit_admin"]:
        raise HTTPException(status_code=403, detail="Access denied")

    return AnalysisTaskResponse(
        id=str(task.id),
        user_id=str(task.user_id),
        task_type=task.task_type,
        status=task.status,
        log_type=task.log_type,
        time_range_start=task.time_range_start,
        time_range_end=task.time_range_end,
        progress_percent=task.progress_percent,
        model_id=str(task.model_id) if task.model_id else None,
        input_tokens=task.input_tokens,
        output_tokens=task.output_tokens,
        result=task.result,
        error_message=task.error_message,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at
    )


@router.get("/tasks/{task_id}/result", response_model=AnalysisResultResponse)
async def get_analysis_result(
    task_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get analysis result"""

    result = await db.execute(
        select(AnalysisTask).where(AnalysisTask.id == UUID(task_id))
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Task not completed, current status: {task.status}"
        )

    # Check access
    if str(task.user_id) != current_user["id"] and \
       current_user["role"] not in ["super_admin", "audit_admin"]:
        raise HTTPException(status_code=403, detail="Access denied")

    task_result = task.result or {}

    return AnalysisResultResponse(
        task_id=str(task.id),
        success=True,
        summary=task_result.get("summary"),
        findings=task_result.get("findings"),
        recommendations=task_result.get("recommendations"),
        input_tokens=task.input_tokens or 0,
        output_tokens=task.output_tokens or 0,
        model_used=task_result.get("model_used", ""),
        duration_ms=task_result.get("duration_ms", 0)
    )


@router.delete("/tasks/{task_id}")
async def cancel_analysis_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Cancel analysis task"""

    result = await db.execute(
        select(AnalysisTask).where(AnalysisTask.id == UUID(task_id))
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if str(task.user_id) != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    if task.status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
        raise HTTPException(
            status_code=400,
            detail="Can only cancel pending or running tasks"
        )

    task.status = TaskStatus.CANCELLED
    await db.commit()

    return {"message": "Task cancelled"}


@router.get("/providers", response_model=List[AIProviderResponse])
async def list_ai_providers(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """List AI providers"""

    result = await db.execute(
        select(AIProvider).order_by(AIProvider.is_default.desc(), AIProvider.name)
    )
    providers = result.scalars().all()

    return [
        AIProviderResponse(
            id=str(p.id),
            name=p.name,
            display_name=p.display_name,
            provider_type=p.provider_type,
            is_active=p.is_active,
            is_default=p.is_default
        )
        for p in providers
    ]


@router.get("/models", response_model=List[AIModelResponse])
async def list_ai_models(
    provider_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """List AI models"""

    query = select(AIModel).where(AIModel.is_active == True)

    if provider_id:
        query = query.where(AIModel.provider_id == UUID(provider_id))

    result = await db.execute(query)
    models = result.scalars().all()

    return [
        AIModelResponse(
            id=str(m.id),
            provider_id=str(m.provider_id),
            model_name=m.model_name,
            display_name=m.display_name,
            max_tokens=m.max_tokens,
            is_active=m.is_active,
            is_default=m.is_default
        )
        for m in models
    ]


async def run_analysis_task(
    task_id: str,
    analysis_type: str,
    model_id: Optional[str],
    provider_id: Optional[str]
):
    """Background task to run AI analysis"""

    from app.database import async_session_factory

    async with async_session_factory() as db:
        try:
            # Initialize AI engine
            await ai_engine.initialize(db)

            # Get logs sample (mock for now)
            task = await db.execute(
                select(AnalysisTask).where(AnalysisTask.id == UUID(task_id))
            )
            task = task.scalar_one()

            logs_sample = await get_logs_sample_for_analysis(
                task.time_range_start,
                task.time_range_end,
                task.log_type,
                task.devices
            )

            # Run analysis
            result = await ai_engine.analyze_logs(
                db,
                UUID(task_id),
                logs_sample,
                analysis_type,
                provider_id,
                model_id
            )

            logger.info(f"Analysis completed for task {task_id}: success={result.success}")

        except Exception as e:
            logger.error(f"Analysis failed for task {task_id}: {e}")

            await db.execute(
                select(AnalysisTask).where(AnalysisTask.id == UUID(task_id))
            )
            task = await db.execute(
                select(AnalysisTask).where(AnalysisTask.id == UUID(task_id))
            )
            # Update task status on error
            await db.commit()