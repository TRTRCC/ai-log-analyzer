"""
System configuration models
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Text, UUID, Integer, JSON
)
from sqlalchemy.orm import relationship

from app.database import Base


class SystemConfig(Base):
    """System configuration model"""
    __tablename__ = "system_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_key = Column(String(100), unique=True, nullable=False, index=True)
    config_value = Column(JSON, nullable=True)
    description = Column(Text, nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<SystemConfig {self.config_key}>"

    def get_value(self, default: Any = None) -> Any:
        """Get configuration value"""
        if self.config_value is None:
            return default
        return self.config_value

    def set_value(self, value: Any):
        """Set configuration value"""
        self.config_value = value


class ScheduledTask(Base):
    """Scheduled task configuration"""
    __tablename__ = "scheduled_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    task_type = Column(String(50), nullable=False)
    cron_expression = Column(String(100), nullable=True)
    interval_minutes = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    config = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ScheduledTask {self.name}>"

    def calculate_next_run(self) -> datetime:
        """Calculate next run time based on cron or interval"""
        from croniter import croniter
        from datetime import datetime

        if self.cron_expression:
            cron = croniter(self.cron_expression, datetime.utcnow())
            return cron.get_next(datetime)
        elif self.interval_minutes:
            if self.last_run:
                return self.last_run + datetime.timedelta(minutes=self.interval_minutes)
            return datetime.utcnow() + datetime.timedelta(minutes=self.interval_minutes)
        return None


class EmailConfig(Base):
    """Email configuration model"""
    __tablename__ = "email_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    smtp_host = Column(String(255), nullable=False)
    smtp_port = Column(Integer, nullable=False, default=587)
    smtp_user = Column(String(100), nullable=True)
    smtp_password_encrypted = Column(Text, nullable=True)
    from_email = Column(String(100), nullable=False)
    use_tls = Column(Boolean, default=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<EmailConfig {self.smtp_host}>"


class FrontendModule(Base):
    """Frontend module configuration"""
    __tablename__ = "frontend_modules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_key = Column(String(50), unique=True, nullable=False)
    module_name = Column(String(100), nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    roles_allowed = Column(JSON, nullable=True)  # List of roles that can access
    config = Column(JSON, nullable=True)
    sort_order = Column(Integer, default=0)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<FrontendModule {self.module_key}>"

    def can_access(self, role: str) -> bool:
        """Check if a role can access this module"""
        if not self.is_enabled:
            return False
        if self.roles_allowed is None:
            return True  # All roles can access
        return role in self.roles_allowed


class StorageConfig(Base):
    """Storage directory configuration"""
    __tablename__ = "storage_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_key = Column(String(50), unique=True, nullable=False)
    directory_path = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    max_size_mb = Column(Integer, nullable=True)
    retention_days = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<StorageConfig {self.config_key}>"


class AIUsageLog(Base):
    """AI usage statistics log"""
    __tablename__ = "ai_usage_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("ai_providers.id"), nullable=True)
    model_id = Column(UUID(as_uuid=True), ForeignKey("ai_models.id"), nullable=True)
    task_id = Column(UUID(as_uuid=True), ForeignKey("analysis_tasks.id"), nullable=True)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    cost = Column(Text, nullable=True)  # JSON with cost breakdown
    request_duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<AIUsageLog {self.id}>"

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens