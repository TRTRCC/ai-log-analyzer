"""
Admin API Routes - System configuration and management
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from app.database import get_db_session
from app.models import (
    SystemConfig, ScheduledTask, EmailConfig,
    FrontendModule, StorageConfig, AIUsageLog,
    AIProvider, AIModel, AuditLog
)
from app.api.auth import get_current_user, get_admin_user, get_super_admin
from app.utils.security import encrypt_value
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


# Request/Response models
class SystemConfigUpdate(BaseModel):
    config_key: str
    config_value: Dict[str, Any]
    description: Optional[str] = None


class EmailConfigCreate(BaseModel):
    smtp_host: str
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    from_email: str
    use_tls: bool = True


class AIProviderCreate(BaseModel):
    name: str
    display_name: Optional[str] = None
    provider_type: str
    api_endpoint: Optional[str] = None
    api_key: str
    is_default: bool = False
    config: Optional[Dict] = None


class AIModelCreate(BaseModel):
    provider_id: str
    model_name: str
    display_name: Optional[str] = None
    max_tokens: Optional[int] = 4000
    cost_per_1k_input: Optional[float] = None
    cost_per_1k_output: Optional[float] = None
    is_default: bool = False


class ScheduledTaskCreate(BaseModel):
    name: str
    task_type: str
    cron_expression: Optional[str] = None
    interval_minutes: Optional[int] = None
    is_active: bool = True
    config: Optional[Dict] = None


class StorageConfigUpdate(BaseModel):
    config_key: str
    directory_path: str
    max_size_mb: Optional[int] = None
    retention_days: Optional[int] = None


class FrontendModuleUpdate(BaseModel):
    module_key: str
    is_enabled: bool
    roles_allowed: Optional[List[str]] = None
    sort_order: Optional[int] = None


# === AI Provider Management ===
@router.post("/ai/providers")
async def create_ai_provider(
    request: AIProviderCreate,
    admin: dict = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Create new AI provider"""

    # Check if name exists
    existing = await db.execute(
        select(AIProvider).where(AIProvider.name == request.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Provider name already exists")

    provider = AIProvider(
        name=request.name,
        display_name=request.display_name or request.name,
        provider_type=request.provider_type,
        api_endpoint=request.api_endpoint,
        api_key_encrypted=encrypt_value(request.api_key) if request.api_key else None,
        is_active=True,
        is_default=request.is_default,
        config=request.config
    )

    db.add(provider)
    await db.commit()
    await db.refresh(provider)

    # If default, unset others
    if request.is_default:
        await db.execute(
            update(AIProvider)
            .where(AIProvider.id != provider.id)
            .values(is_default=False)
        )
        await db.commit()

    logger.info(f"AI provider created: {request.name}")

    return {
        "id": str(provider.id),
        "name": provider.name,
        "provider_type": provider.provider_type,
        "is_default": provider.is_default
    }


@router.put("/ai/providers/{provider_id}")
async def update_ai_provider(
    provider_id: str,
    name: Optional[str] = None,
    api_endpoint: Optional[str] = None,
    api_key: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_default: Optional[bool] = None,
    admin: dict = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Update AI provider"""

    result = await db.execute(
        select(AIProvider).where(AIProvider.id == UUID(provider_id))
    )
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if name:
        provider.name = name
    if api_endpoint:
        provider.api_endpoint = api_endpoint
    if api_key:
        provider.api_key_encrypted = encrypt_value(api_key)
    if is_active is not None:
        provider.is_active = is_active
    if is_default is not None:
        if is_default:
            # Unset other defaults
            await db.execute(
                update(AIProvider)
                .where(AIProvider.id != provider.id)
                .values(is_default=False)
            )
        provider.is_default = is_default

    await db.commit()

    return {"message": "Provider updated"}


@router.delete("/ai/providers/{provider_id}")
async def delete_ai_provider(
    provider_id: str,
    admin: dict = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Delete AI provider"""

    result = await db.execute(
        delete(AIProvider).where(AIProvider.id == UUID(provider_id))
    )
    await db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Provider not found")

    return {"message": "Provider deleted"}


# === AI Model Management ===
@router.post("/ai/models")
async def create_ai_model(
    request: AIModelCreate,
    admin: dict = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Create new AI model"""

    model = AIModel(
        provider_id=UUID(request.provider_id),
        model_name=request.model_name,
        display_name=request.display_name or request.model_name,
        max_tokens=request.max_tokens,
        cost_per_1k_input_tokens=request.cost_per_1k_input,
        cost_per_1k_output_tokens=request.cost_per_1k_output,
        is_active=True,
        is_default=request.is_default
    )

    db.add(model)
    await db.commit()
    await db.refresh(model)

    return {
        "id": str(model.id),
        "model_name": model.model_name,
        "provider_id": str(model.provider_id)
    }


@router.delete("/ai/models/{model_id}")
async def delete_ai_model(
    model_id: str,
    admin: dict = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Delete AI model"""

    result = await db.execute(
        delete(AIModel).where(AIModel.id == UUID(model_id))
    )
    await db.commit()

    return {"message": "Model deleted"}


# === Email Configuration ===
@router.get("/email")
async def get_email_config(
    admin: dict = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Get email configuration"""

    result = await db.execute(select(EmailConfig))
    configs = result.scalars().all()

    return [
        {
            "id": str(c.id),
            "smtp_host": c.smtp_host,
            "smtp_port": c.smtp_port,
            "smtp_user": c.smtp_user,
            "from_email": c.from_email,
            "use_tls": c.use_tls,
            "is_active": c.is_active
        }
        for c in configs
    ]


@router.post("/email")
async def create_email_config(
    request: EmailConfigCreate,
    admin: dict = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Create email configuration"""

    config = EmailConfig(
        smtp_host=request.smtp_host,
        smtp_port=request.smtp_port,
        smtp_user=request.smtp_user,
        smtp_password_encrypted=encrypt_value(request.smtp_password) if request.smtp_password else None,
        from_email=request.from_email,
        use_tls=request.use_tls,
        is_active=True
    )

    db.add(config)
    await db.commit()

    return {"message": "Email configuration created"}


@router.put("/email/{config_id}")
async def update_email_config(
    config_id: str,
    request: EmailConfigCreate,
    admin: dict = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Update email configuration"""

    result = await db.execute(
        select(EmailConfig).where(EmailConfig.id == UUID(config_id))
    )
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    config.smtp_host = request.smtp_host
    config.smtp_port = request.smtp_port
    config.smtp_user = request.smtp_user
    config.smtp_password_encrypted = encrypt_value(request.smtp_password) if request.smtp_password else None
    config.from_email = request.from_email
    config.use_tls = request.use_tls

    await db.commit()

    return {"message": "Email configuration updated"}


# === Scheduled Tasks ===
@router.get("/tasks")
async def list_scheduled_tasks(
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db_session)
):
    """List scheduled tasks"""

    result = await db.execute(select(ScheduledTask))
    tasks = result.scalars().all()

    return [
        {
            "id": str(t.id),
            "name": t.name,
            "task_type": t.task_type,
            "cron_expression": t.cron_expression,
            "interval_minutes": t.interval_minutes,
            "is_active": t.is_active,
            "last_run": t.last_run,
            "next_run": t.next_run
        }
        for t in tasks
    ]


@router.post("/tasks")
async def create_scheduled_task(
    request: ScheduledTaskCreate,
    admin: dict = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Create scheduled task"""

    task = ScheduledTask(
        name=request.name,
        task_type=request.task_type,
        cron_expression=request.cron_expression,
        interval_minutes=request.interval_minutes,
        is_active=request.is_active,
        config=request.config
    )

    db.add(task)
    await db.commit()

    return {"message": "Scheduled task created", "id": str(task.id)}}


@router.put("/tasks/{task_id}")
async def update_scheduled_task(
    task_id: str,
    is_active: Optional[bool] = None,
    cron_expression: Optional[str] = None,
    admin: dict = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Update scheduled task"""

    result = await db.execute(
        select(ScheduledTask).where(ScheduledTask.id == UUID(task_id))
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if is_active is not None:
        task.is_active = is_active
    if cron_expression:
        task.cron_expression = cron_expression

    await db.commit()

    return {"message": "Scheduled task updated"}


# === Storage Configuration ===
@router.get("/storage")
async def list_storage_configs(
    admin: dict = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """List storage configurations"""

    result = await db.execute(select(StorageConfig))
    configs = result.scalars().all()

    return [
        {
            "id": str(c.id),
            "config_key": c.config_key,
            "directory_path": c.directory_path,
            "description": c.description,
            "max_size_mb": c.max_size_mb,
            "retention_days": c.retention_days,
            "is_active": c.is_active
        }
        for c in configs
    ]


@router.put("/storage")
async def update_storage_config(
    request: StorageConfigUpdate,
    admin: dict = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Update storage configuration"""

    result = await db.execute(
        select(StorageConfig).where(StorageConfig.config_key == request.config_key)
    )
    config = result.scalar_one_or_none()

    if config:
        config.directory_path = request.directory_path
        config.max_size_mb = request.max_size_mb
        config.retention_days = request.retention_days
    else:
        config = StorageConfig(
            config_key=request.config_key,
            directory_path=request.directory_path,
            max_size_mb=request.max_size_mb,
            retention_days=request.retention_days
        )
        db.add(config)

    await db.commit()

    return {"message": "Storage configuration updated"}


# === Frontend Modules ===
@router.get("/frontend/modules")
async def list_frontend_modules(
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db_session)
):
    """List frontend modules"""

    result = await db.execute(
        select(FrontendModule).order_by(FrontendModule.sort_order)
    )
    modules = result.scalars().all()

    return [
        {
            "id": str(m.id),
            "module_key": m.module_key,
            "module_name": m.module_name,
            "is_enabled": m.is_enabled,
            "roles_allowed": m.roles_allowed,
            "sort_order": m.sort_order
        }
        for m in modules
    ]


@router.put("/frontend/modules")
async def update_frontend_module(
    request: FrontendModuleUpdate,
    admin: dict = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Update frontend module"""

    result = await db.execute(
        select(FrontendModule).where(FrontendModule.module_key == request.module_key)
    )
    module = result.scalar_one_or_none()

    if module:
        module.is_enabled = request.is_enabled
        module.roles_allowed = request.roles_allowed
        module.sort_order = request.sort_order
    else:
        module = FrontendModule(
            module_key=request.module_key,
            module_name=request.module_key,
            is_enabled=request.is_enabled,
            roles_allowed=request.roles_allowed,
            sort_order=request.sort_order
        )
        db.add(module)

    await db.commit()

    return {"message": "Frontend module updated"}


# === Audit Logs ===
@router.get("/audit/logs")
async def list_audit_logs(
    action: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db_session)
):
    """List audit logs"""

    query = select(AuditLog)

    if action:
        query = query.where(AuditLog.action == action)
    if user_id:
        query = query.where(AuditLog.user_id == UUID(user_id))
    if start_time:
        query = query.where(AuditLog.created_at >= start_time)
    if end_time:
        query = query.where(AuditLog.created_at <= end_time)

    query = query.order_by(AuditLog.created_at.desc())
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    logs = result.scalars().all()

    return [
        {
            "id": str(l.id),
            "user_id": str(l.user_id) if l.user_id else None,
            "action": l.action,
            "resource_type": l.resource_type,
            "resource_id": str(l.resource_id) if l.resource_id else None,
            "details": json.loads(l.details) if l.details else None,
            "ip_address": l.ip_address,
            "created_at": l.created_at
        }
        for l in logs
    ]


# === AI Usage Statistics ===
@router.get("/ai/usage")
async def get_ai_usage_stats(
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    provider_id: Optional[str] = Query(None),
    limit: int = Query(default=100),
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get AI usage statistics"""

    query = select(AIUsageLog)

    if start_time:
        query = query.where(AIUsageLog.created_at >= start_time)
    if end_time:
        query = query.where(AIUsageLog.created_at <= end_time)
    if provider_id:
        query = query.where(AIUsageLog.provider_id == UUID(provider_id))

    query = query.order_by(AIUsageLog.created_at.desc())
    query = query.limit(limit)

    result = await db.execute(query)
    logs = result.scalars().all()

    # Calculate totals
    total_input = sum(l.input_tokens for l in logs)
    total_output = sum(l.output_tokens for l in logs)

    return {
        "logs": [
            {
                "id": str(l.id),
                "user_id": str(l.user_id) if l.user_id else None,
                "provider_id": str(l.provider_id) if l.provider_id else None,
                "model_id": str(l.model_id) if l.model_id else None,
                "task_id": str(l.task_id) if l.task_id else None,
                "input_tokens": l.input_tokens,
                "output_tokens": l.output_tokens,
                "request_duration_ms": l.request_duration_ms,
                "created_at": l.created_at
            }
            for l in logs
        ],
        "summary": {
            "total_requests": len(logs),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_input + total_output
        }
    }


# === System Configuration ===
@router.get("/system/config")
async def list_system_configs(
    admin: dict = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """List system configurations"""

    result = await db.execute(select(SystemConfig))
    configs = result.scalars().all()

    return [
        {
            "id": str(c.id),
            "config_key": c.config_key,
            "config_value": c.config_value,
            "description": c.description,
            "updated_at": c.updated_at
        }
        for c in configs
    ]


@router.put("/system/config")
async def update_system_config(
    request: SystemConfigUpdate,
    admin: dict = Depends(get_super_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Update system configuration"""

    result = await db.execute(
        select(SystemConfig).where(SystemConfig.config_key == request.config_key)
    )
    config = result.scalar_one_or_none()

    if config:
        config.config_value = request.config_value
        config.description = request.description
        config.updated_by = UUID(admin["id"])
    else:
        config = SystemConfig(
            config_key=request.config_key,
            config_value=request.config_value,
            description=request.description,
            updated_by=UUID(admin["id"])
        )
        db.add(config)

    await db.commit()

    return {"message": "System configuration updated"}