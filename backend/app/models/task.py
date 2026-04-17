"""
Analysis task and report models
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Text, UUID, Integer, JSON, Date, ARRAY
)
from sqlalchemy.dialects.postgresql import TSRANGE
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class TaskType(str, enum.Enum):
    """Analysis task type"""
    AUTO = "auto"  # Automatic scheduled task
    MANUAL_FULL = "manual_full"  # Manual full analysis
    MANUAL_PARTIAL = "manual_partial"  # Manual partial analysis (time/device range)
    DAILY_REPORT = "daily_report"  # Daily report generation


class TaskStatus(str, enum.Enum):
    """Task status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LogType(str, enum.Enum):
    """Log type for analysis"""
    NETWORK = "network"
    SERVER = "server"
    K8S = "k8s"
    ALL = "all"


class AnalysisTask(Base):
    """Analysis task model"""
    __tablename__ = "analysis_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    task_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default=TaskStatus.PENDING)
    log_type = Column(String(20), nullable=False, default=LogType.ALL)
    time_range_start = Column(DateTime, nullable=True)
    time_range_end = Column(DateTime, nullable=True)
    devices = Column(ARRAY(String), nullable=True)  # List of device/host names
    model_id = Column(UUID(as_uuid=True), ForeignKey("ai_models.id"), nullable=True)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("ai_providers.id"), nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    estimated_cost = Column(Text, nullable=True)  # JSON string with cost breakdown
    result = Column(JSON, nullable=True)  # Analysis result
    error_message = Column(Text, nullable=True)
    progress_percent = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="tasks")
    model = relationship("AIModel", back_populates="tasks")
    provider = relationship("AIProvider", back_populates="tasks")
    report = relationship("Report", back_populates="task", uselist=False)

    def __repr__(self):
        return f"<AnalysisTask {self.id}>"

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate task duration in seconds"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def is_running(self) -> bool:
        return self.status == TaskStatus.RUNNING

    def is_completed(self) -> bool:
        return self.status == TaskStatus.COMPLETED

    def is_failed(self) -> bool:
        return self.status == TaskStatus.FAILED


class ReportType(str, enum.Enum):
    """Report type"""
    DAILY = "daily"
    ADHOC = "adhoc"
    INCIDENT = "incident"


class Report(Base):
    """Analysis report model"""
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("analysis_tasks.id"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    report_type = Column(String(20), nullable=False)
    report_date = Column(Date, nullable=True, index=True)
    title = Column(String(255), nullable=True)
    content = Column(JSON, nullable=True)  # Report content as JSON
    summary = Column(Text, nullable=True)
    file_path = Column(String(500), nullable=True)  # Path to saved report file
    file_format = Column(String(10), default="pdf")
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    task = relationship("AnalysisTask", back_populates="report")
    user = relationship("User", back_populates="reports")

    def __repr__(self):
        return f"<Report {self.title or self.id}>"


class ReportSubscription(Base):
    """Report email subscription"""
    __tablename__ = "report_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    report_type = Column(String(20), nullable=False)
    email = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="subscriptions")

    def __repr__(self):
        return f"<ReportSubscription {self.email}>"