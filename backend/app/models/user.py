"""
User models for AI Log Analyzer
"""

import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Enum, Text, UUID, Integer
)
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class UserRole(str, enum.Enum):
    """User role enumeration"""
    SUPER_ADMIN = "super_admin"
    AUDIT_ADMIN = "audit_admin"
    DEPT_ADMIN = "dept_admin"
    NETWORK_USER = "network_user"
    SERVER_USER = "server_user"
    K8S_USER = "k8s_user"


class User(Base):
    """User model"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.SERVER_USER)
    department_id = Column(UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    department = relationship("Department", back_populates="users")
    reports = relationship("Report", back_populates="user")
    tasks = relationship("AnalysisTask", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")
    subscriptions = relationship("ReportSubscription", back_populates="user")

    def __repr__(self):
        return f"<User {self.username}>"

    @property
    def is_admin(self) -> bool:
        return self.role in [UserRole.SUPER_ADMIN, UserRole.AUDIT_ADMIN, UserRole.DEPT_ADMIN]

    def can_access_log_type(self, log_type: str) -> bool:
        """Check if user can access specific log type"""
        if self.role == UserRole.SUPER_ADMIN or self.role == UserRole.AUDIT_ADMIN:
            return True

        if self.role == UserRole.NETWORK_USER and log_type == "network":
            return True
        if self.role == UserRole.SERVER_USER and log_type == "server":
            return True
        if self.role == UserRole.K8S_USER and log_type == "k8s":
            return True

        return False

    def can_create_ai_task(self) -> bool:
        """Check if user can create AI analysis task"""
        return True  # All users can create tasks

    def can_view_all_reports(self) -> bool:
        """Check if user can view all reports"""
        return self.role in [UserRole.SUPER_ADMIN, UserRole.AUDIT_ADMIN]

    def can_manage_users(self) -> bool:
        """Check if user can manage other users"""
        return self.role in [UserRole.SUPER_ADMIN, UserRole.DEPT_ADMIN]

    def can_configure_system(self) -> bool:
        """Check if user can configure system settings"""
        return self.role == UserRole.SUPER_ADMIN


class Department(Base):
    """Department model"""
    __tablename__ = "departments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    users = relationship("User", back_populates="department")

    def __repr__(self):
        return f"<Department {self.name}>"


class AuditLog(Base):
    """Audit log model for tracking user actions"""
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action = Column(String(50), nullable=False, index=True)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    details = Column(Text, nullable=True)  # JSON string
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    user = relationship("User", back_populates="audit_logs")

    def __repr__(self):
        return f"<AuditLog {self.action} by {self.user_id}>"

    @classmethod
    def create(cls, user_id: str, action: str, resource_type: str = None,
               resource_id: str = None, details: dict = None,
               ip_address: str = None, user_agent: str = None):
        """Create an audit log entry"""
        import json
        return cls(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(details) if details else None,
            ip_address=ip_address,
            user_agent=user_agent,
        )