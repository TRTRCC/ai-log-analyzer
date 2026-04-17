"""
Models package initialization
"""

from app.models.user import User, UserRole, Department, AuditLog
from app.models.ai_provider import AIProvider, AIModel, ProviderType
from app.models.task import AnalysisTask, Report, ReportSubscription, TaskType, TaskStatus, LogType, ReportType
from app.models.system import (
    SystemConfig,
    ScheduledTask,
    EmailConfig,
    FrontendModule,
    StorageConfig,
    AIUsageLog,
)

__all__ = [
    # User models
    "User",
    "UserRole",
    "Department",
    "AuditLog",
    # AI models
    "AIProvider",
    "AIModel",
    "ProviderType",
    # Task models
    "AnalysisTask",
    "TaskType",
    "TaskStatus",
    "LogType",
    "Report",
    "ReportType",
    "ReportSubscription",
    # System models
    "SystemConfig",
    "ScheduledTask",
    "EmailConfig",
    "FrontendModule",
    "StorageConfig",
    "AIUsageLog",
]