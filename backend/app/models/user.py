"""
User models for AI Log Analyzer - 等保三合规版本
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Enum, Text, UUID, Integer, JSON
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
    """User model - 等保三增强版"""
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

    # === 等保三安全字段 ===
    # 登录失败锁定机制
    login_fail_count = Column(Integer, default=0, nullable=False)
    login_fail_first_time = Column(DateTime, nullable=True)
    locked_until = Column(DateTime, nullable=True)
    lock_reason = Column(String(100), nullable=True)

    # 密码管理
    password_changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    password_expires_at = Column(DateTime, nullable=True)
    force_password_change = Column(Boolean, default=False, nullable=False)
    password_history = Column(JSON, nullable=True)  # 存储最近5次密码哈希，防止重复使用

    # 双因子认证(2FA/TOTP)
    two_factor_enabled = Column(Boolean, default=False, nullable=False)
    two_factor_secret_encrypted = Column(String(255), nullable=True)
    two_factor_backup_codes = Column(JSON, nullable=True)  # 10个备用码
    two_factor_verified_at = Column(DateTime, nullable=True)

    # 会话管理
    max_concurrent_sessions = Column(Integer, default=5, nullable=False)
    session_timeout_minutes = Column(Integer, default=30, nullable=False)

    # Relationships
    department = relationship("Department", back_populates="users")
    reports = relationship("Report", back_populates="user")
    tasks = relationship("AnalysisTask", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")
    subscriptions = relationship("ReportSubscription", back_populates="user")
    sessions = relationship("UserSession", back_populates="user")

    def __repr__(self):
        return f"<User {self.username}>"

    @property
    def is_admin(self) -> bool:
        return self.role in [UserRole.SUPER_ADMIN, UserRole.AUDIT_ADMIN, UserRole.DEPT_ADMIN]

    @property
    def is_locked(self) -> bool:
        """检查账户是否被锁定"""
        return self.locked_until is not None and self.locked_until > datetime.utcnow()

    @property
    def password_expired(self) -> bool:
        """检查密码是否过期"""
        if self.password_expires_at is None:
            return False
        return self.password_expires_at < datetime.utcnow()

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


class UserSession(Base):
    """用户会话表 - 等保三要求"""
    __tablename__ = "user_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    session_token_hash = Column(String(64), unique=True, nullable=False, index=True)
    refresh_token_hash = Column(String(64), unique=True, nullable=True, index=True)
    device_info = Column(JSON, nullable=True)  # {device_type, os, browser}
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    terminated_at = Column(DateTime, nullable=True)
    terminate_reason = Column(String(50), nullable=True)

    # Relationships
    user = relationship("User", back_populates="sessions")

    def __repr__(self):
        return f"<UserSession {self.user_id}>"

    @property
    def is_expired(self) -> bool:
        """检查会话是否过期"""
        timeout_minutes = self.user.session_timeout_minutes if self.user else 30
        return self.last_activity < datetime.utcnow() - timedelta(minutes=timeout_minutes)


class SecurityEvent(Base):
    """安全事件表 - 入侵检测和告警"""
    __tablename__ = "security_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), nullable=False)  # critical, high, medium, low
    source_ip = Column(String(45), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    details = Column(JSON, nullable=True)
    action_taken = Column(String(50), nullable=True)  # blocked, alerted, logged
    resolved = Column(Boolean, default=False, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<SecurityEvent {self.event_type}>"


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
    """Audit log model - 等保三防篡改增强版"""
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

    # === 等保三防篡改字段 ===
    log_hash = Column(String(64), nullable=False)  # 当前日志SHA256哈希
    prev_hash = Column(String(64), nullable=True)  # 前一条日志哈希（链式校验）
    signature = Column(Text, nullable=True)  # RSA数字签名
    sequence_number = Column(Integer, nullable=False)  # 日志序列号

    # Relationships
    user = relationship("User", back_populates="audit_logs")

    def __repr__(self):
        return f"<AuditLog {self.action} by {self.user_id}>"

    @classmethod
    def create(cls, user_id: str, action: str, resource_type: str = None,
               resource_id: str = None, details: dict = None,
               ip_address: str = None, user_agent: str = None,
               prev_hash: str = None, sequence_number: int = 0):
        """Create an audit log entry with tamper protection"""
        import json
        import hashlib
        from datetime import datetime

        content = json.dumps({
            "user_id": str(user_id) if user_id else None,
            "action": action,
            "resource_type": resource_type,
            "resource_id": str(resource_id) if resource_id else None,
            "details": details,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "timestamp": datetime.utcnow().isoformat(),
            "prev_hash": prev_hash or "0000000000000000000000000000000000000000000000000000000000000000",
            "sequence_number": sequence_number
        }, sort_keys=True)

        log_hash = hashlib.sha256(content.encode()).hexdigest()

        return cls(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(details) if details else None,
            ip_address=ip_address,
            user_agent=user_agent,
            log_hash=log_hash,
            prev_hash=prev_hash,
            sequence_number=sequence_number,
        )