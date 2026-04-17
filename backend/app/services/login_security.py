"""
Login Security Service - 等保三登录失败锁定机制
"""

import hashlib
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
import redis

from app.models.user import User, UserSession, SecurityEvent
from app.config import settings


class LoginSecurityService:
    """登录安全服务 - 实现等保三要求的登录失败锁定"""

    # 等保三配置参数
    MAX_LOGIN_FAILURES = 5  # 最大失败次数
    LOCKOUT_DURATION_MINUTES = 30  # 锁定时长（分钟）
    FAILURE_WINDOW_MINUTES = 15  # 失败计数窗口（分钟）

    def __init__(self, db: Session, redis_client: redis.Redis = None):
        self.db = db
        self.redis = redis_client

    def record_login_failure(
        self,
        user: User,
        ip_address: str,
        reason: str = "invalid_password"
    ) -> dict:
        """记录登录失败"""
        now = datetime.utcnow()

        # 检查是否在失败窗口内
        if user.login_fail_first_time:
            window_end = user.login_fail_first_time + timedelta(minutes=self.FAILURE_WINDOW_MINUTES)
            if now > window_end:
                # 窗口过期，重置计数
                user.login_fail_count = 1
                user.login_fail_first_time = now
            else:
                # 窗口内，增加计数
                user.login_fail_count += 1
        else:
            # 首次失败
            user.login_fail_count = 1
            user.login_fail_first_time = now

        # 检查是否需要锁定
        if user.login_fail_count >= self.MAX_LOGIN_FAILURES:
            lockout_until = now + timedelta(minutes=self.LOCKOUT_DURATION_MINUTES)
            user.locked_until = lockout_until
            user.lock_reason = f"exceeded_max_failures:{user.login_fail_count}"

            # 记录安全事件
            self._create_security_event(
                event_type="account_locked",
                severity="high",
                user_id=user.id,
                source_ip=ip_address,
                details={
                    "failure_count": user.login_fail_count,
                    "lockout_duration_minutes": self.LOCKOUT_DURATION_MINUTES,
                    "reason": reason
                },
                action_taken="locked"
            )

        self.db.commit()

        return {
            "failure_count": user.login_fail_count,
            "is_locked": user.is_locked,
            "locked_until": user.locked_until.isoformat() if user.locked_until else None,
            "remaining_attempts": self.MAX_LOGIN_FAILURES - user.login_fail_count
        }

    def check_login_allowed(self, user: User) -> dict:
        """检查是否允许登录"""
        now = datetime.utcnow()

        # 检查账户是否被锁定
        if user.is_locked:
            return {
                "allowed": False,
                "reason": "account_locked",
                "locked_until": user.locked_until.isoformat() if user.locked_until else None,
                "lock_reason": user.lock_reason
            }

        # 检查密码是否过期
        if user.password_expired:
            return {
                "allowed": False,
                "reason": "password_expired",
                "password_expires_at": user.password_expires_at.isoformat() if user.password_expires_at else None
            }

        # 检查是否需要强制修改密码
        if user.force_password_change:
            return {
                "allowed": False,
                "reason": "force_password_change"
            }

        return {"allowed": True}

    def clear_login_failures(self, user: User):
        """登录成功后清除失败记录"""
        user.login_fail_count = 0
        user.login_fail_first_time = None
        self.db.commit()

    def unlock_account(self, user: User, unlocked_by: User, reason: str = "manual_unlock"):
        """手动解锁账户"""
        user.locked_until = None
        user.lock_reason = None
        user.login_fail_count = 0
        user.login_fail_first_time = None
        self.db.commit()

        # 记录安全事件
        self._create_security_event(
            event_type="account_unlocked",
            severity="medium",
            user_id=user.id,
            details={
                "unlocked_by": str(unlocked_by.id),
                "reason": reason
            },
            action_taken="unlocked"
        )

    def check_brute_force_attack(self, ip_address: str) -> dict:
        """检查IP暴力破解攻击"""
        # 使用Redis追踪IP失败次数
        if self.redis:
            key = f"login_fail_ip:{ip_address}"
            fail_count = self.redis.get(key)
            if fail_count and int(fail_count) >= 10:
                # 记录安全事件
                self._create_security_event(
                    event_type="brute_force_detected",
                    severity="critical",
                    source_ip=ip_address,
                    details={"failure_count": int(fail_count)},
                    action_taken="blocked"
                )
                return {
                    "blocked": True,
                    "reason": "brute_force_detected",
                    "failure_count": int(fail_count)
                }

        return {"blocked": False}

    def record_ip_failure(self, ip_address: str):
        """记录IP失败（Redis缓存）"""
        if self.redis:
            key = f"login_fail_ip:{ip_address}"
            self.redis.incr(key)
            self.redis.expire(key, timedelta(minutes=self.FAILURE_WINDOW_MINUTES).seconds)

    def clear_ip_failures(self, ip_address: str):
        """清除IP失败记录"""
        if self.redis:
            key = f"login_fail_ip:{ip_address}"
            self.redis.delete(key)

    def _create_security_event(
        self,
        event_type: str,
        severity: str,
        user_id: Optional[str] = None,
        source_ip: Optional[str] = None,
        details: Optional[dict] = None,
        action_taken: Optional[str] = None
    ) -> SecurityEvent:
        """创建安全事件记录"""
        event = SecurityEvent(
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            source_ip=source_ip,
            details=details,
            action_taken=action_taken
        )
        self.db.add(event)
        self.db.commit()
        return event


class SessionManager:
    """会话管理 - 等保三会话控制"""

    def __init__(self, db: Session, redis_client: redis.Redis = None):
        self.db = db
        self.redis = redis_client

    def create_session(
        self,
        user: User,
        session_token: str,
        refresh_token: Optional[str] = None,
        device_info: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> UserSession:
        """创建新会话"""
        # 检查并发会话限制
        active_sessions = self.db.query(UserSession).filter(
            UserSession.user_id == user.id,
            UserSession.is_active == True
        ).count()

        if active_sessions >= user.max_concurrent_sessions:
            # 终止最旧的会话
            oldest = self.db.query(UserSession).filter(
                UserSession.user_id == user.id,
                UserSession.is_active == True
            ).order_by(UserSession.created_at.asc()).first()
            if oldest:
                self.terminate_session(oldest, reason="max_sessions_exceeded")

        # 创建会话记录
        session = UserSession(
            user_id=user.id,
            session_token_hash=self._hash_token(session_token),
            refresh_token_hash=self._hash_token(refresh_token) if refresh_token else None,
            device_info=device_info,
            ip_address=ip_address,
            user_agent=user_agent
        )
        self.db.add(session)
        self.db.commit()

        # 在Redis中存储活跃会话
        if self.redis:
            self.redis.setex(
                f"session:{self._hash_token(session_token)}",
                timedelta(minutes=user.session_timeout_minutes).seconds,
                str(user.id)
            )

        return session

    def validate_session(self, session_token: str) -> Optional[UserSession]:
        """验证会话"""
        token_hash = self._hash_token(session_token)

        # 先检查Redis
        if self.redis:
            user_id = self.redis.get(f"session:{token_hash}")
            if not user_id:
                return None

        # 查询数据库
        session = self.db.query(UserSession).filter(
            UserSession.session_token_hash == token_hash,
            UserSession.is_active == True
        ).first()

        if not session:
            return None

        # 检查是否过期
        if session.is_expired:
            self.terminate_session(session, reason="expired")
            return None

        # 更新最后活动时间
        session.last_activity = datetime.utcnow()
        self.db.commit()

        # 刷新Redis TTL
        if self.redis:
            self.redis.setex(
                f"session:{token_hash}",
                timedelta(minutes=session.user.session_timeout_minutes).seconds,
                str(session.user_id)
            )

        return session

    def terminate_session(self, session: UserSession, reason: str = "logout"):
        """终止会话"""
        session.is_active = False
        session.terminated_at = datetime.utcnow()
        session.terminate_reason = reason
        self.db.commit()

        # 从Redis删除
        if self.redis:
            self.redis.delete(f"session:{session.session_token_hash}")
            if session.refresh_token_hash:
                self.redis.delete(f"refresh:{session.refresh_token_hash}")

    def terminate_all_sessions(self, user: User, reason: str = "force_logout"):
        """终止用户所有会话"""
        sessions = self.db.query(UserSession).filter(
            UserSession.user_id == user.id,
            UserSession.is_active == True
        ).all()

        for session in sessions:
            self.terminate_session(session, reason)

    def get_active_sessions(self, user: User) -> list:
        """获取用户活跃会话"""
        return self.db.query(UserSession).filter(
            UserSession.user_id == user.id,
            UserSession.is_active == True
        ).order_by(UserSession.last_activity.desc()).all()

    def _hash_token(self, token: str) -> str:
        """Token哈希"""
        return hashlib.sha256(token.encode()).hexdigest()