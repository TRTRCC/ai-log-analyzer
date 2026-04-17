"""
Security API Routes - 等保三安全功能端点
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db_sync
from app.models.user import User, UserSession, SecurityEvent
from app.services.login_security import LoginSecurityService, SessionManager
from app.services.password_validator import PasswordValidator, PasswordChangeService
from app.services.two_factor_auth import TOTPService, TwoFactorAuthService
from app.services.token_blacklist import TokenBlacklistService, RefreshTokenService, TokenRevocationManager
from app.api.auth import get_current_user, get_admin_user, get_super_admin
from app.config import settings
import redis

router = APIRouter()
security = HTTPBearer()


# Redis client
def get_redis_client():
    return redis.Redis(host='redis', port=6379, db=1, decode_responses=False)


# === 2FA/TOTP端点 ===

class TOTPSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    backup_codes: List[str]


class TOTPVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=8)


class TOTPStatusResponse(BaseModel):
    enabled: bool
    verified_at: Optional[str] = None
    backup_codes_remaining: int


@router.post("/2fa/setup", response_model=TOTPSetupResponse)
async def setup_two_factor(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_sync)
):
    """启用双因子认证 - 第一步：生成密钥和备用码"""
    user = db.query(User).filter(User.id == UUID(current_user["id"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    totp_service = TOTPService()
    auth_service = TwoFactorAuthService(db, totp_service)

    result = auth_service.setup_two_factor(user)

    return TOTPSetupResponse(
        secret=result["secret"],
        provisioning_uri=result["provisioning_uri"],
        backup_codes=result["backup_codes"]
    )


@router.post("/2fa/verify")
async def verify_and_enable_two_factor(
    request: TOTPVerifyRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_sync)
):
    """验证并正式启用双因子认证"""
    user = db.query(User).filter(User.id == UUID(current_user["id"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    totp_service = TOTPService()
    auth_service = TwoFactorAuthService(db, totp_service)

    result = auth_service.verify_and_enable(user, request.code)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "验证失败")
        )

    return {"message": "双因子认证已启用", "success": True}


@router.post("/2fa/login-verify")
async def verify_two_factor_login(
    request: TOTPVerifyRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_sync)
):
    """登录时验证双因子"""
    user = db.query(User).filter(User.id == UUID(current_user["id"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    totp_service = TOTPService()
    auth_service = TwoFactorAuthService(db, totp_service)

    result = auth_service.verify_login(user, request.code)

    if not result["valid"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "验证失败")
        )

    return {
        "valid": True,
        "method": result.get("method", "totp"),
        "remaining_codes": result.get("remaining_codes", None)
    }


@router.get("/2fa/status", response_model=TOTPStatusResponse)
async def get_two_factor_status(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_sync)
):
    """获取双因子认证状态"""
    user = db.query(User).filter(User.id == UUID(current_user["id"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    totp_service = TOTPService()
    auth_service = TwoFactorAuthService(db, totp_service)

    result = auth_service.get_status(user)

    return TOTPStatusResponse(
        enabled=result["enabled"],
        verified_at=result["verified_at"],
        backup_codes_remaining=result["backup_codes_remaining"]
    )


@router.post("/2fa/disable")
async def disable_two_factor(
    request: TOTPVerifyRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_sync)
):
    """禁用双因子认证"""
    user = db.query(User).filter(User.id == UUID(current_user["id"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    totp_service = TOTPService()
    auth_service = TwoFactorAuthService(db, totp_service)

    result = auth_service.disable_two_factor(user, request.code)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "操作失败")
        )

    return {"message": "双因子认证已禁用", "success": True}


@router.post("/2fa/regenerate-backup-codes", response_model=TOTPSetupResponse)
async def regenerate_backup_codes(
    request: TOTPVerifyRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_sync)
):
    """重新生成备用码"""
    user = db.query(User).filter(User.id == UUID(current_user["id"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    totp_service = TOTPService()
    auth_service = TwoFactorAuthService(db, totp_service)

    result = auth_service.regenerate_backup_codes(user, request.code)

    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "操作失败")
        )

    return TOTPSetupResponse(
        secret="",
        provisioning_uri="",
        backup_codes=result["backup_codes"]
    )


# === 会话管理端点 ===

class SessionInfo(BaseModel):
    id: str
    device_info: Optional[dict] = None
    ip_address: Optional[str] = None
    created_at: datetime
    last_activity: datetime
    is_active: bool


class SessionListResponse(BaseModel):
    sessions: List[SessionInfo]
    max_sessions: int
    timeout_minutes: int


@router.get("/sessions", response_model=SessionListResponse)
async def get_active_sessions(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_sync),
    redis_client: redis.Redis = Depends(get_redis_client)
):
    """获取用户活跃会话列表"""
    user = db.query(User).filter(User.id == UUID(current_user["id"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    session_manager = SessionManager(db, redis_client)
    sessions = session_manager.get_active_sessions(user)

    return SessionListResponse(
        sessions=[
            SessionInfo(
                id=str(s.id),
                device_info=s.device_info,
                ip_address=s.ip_address,
                created_at=s.created_at,
                last_activity=s.last_activity,
                is_active=s.is_active
            )
            for s in sessions
        ],
        max_sessions=user.max_concurrent_sessions,
        timeout_minutes=user.session_timeout_minutes
    )


@router.delete("/sessions/{session_id}")
async def terminate_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_sync),
    redis_client: redis.Redis = Depends(get_redis_client)
):
    """终止指定会话"""
    session = db.query(UserSession).filter(
        UserSession.id == UUID(session_id),
        UserSession.user_id == UUID(current_user["id"])
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session_manager = SessionManager(db, redis_client)
    session_manager.terminate_session(session, reason="user_terminated")

    return {"message": "Session terminated"}


@router.post("/sessions/logout-all")
async def logout_all_sessions(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_sync),
    redis_client: redis.Redis = Depends(get_redis_client)
):
    """注销所有会话"""
    user = db.query(User).filter(User.id == UUID(current_user["id"])).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    session_manager = SessionManager(db, redis_client)
    session_manager.terminate_all_sessions(user, reason="logout_all")

    return {"message": "All sessions terminated"}


# === 账户解锁端点（管理员） ===

class UnlockRequest(BaseModel):
    reason: str = Field(default="manual_unlock", max_length=100)


@router.post("/admin/unlock-user/{user_id}")
async def unlock_user_account(
    user_id: str,
    request: UnlockRequest,
    admin: dict = Depends(get_admin_user),
    db: Session = Depends(get_db_sync),
    redis_client: redis.Redis = Depends(get_redis_client)
):
    """解锁用户账户（管理员）"""
    user = db.query(User).filter(User.id == UUID(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    admin_user = db.query(User).filter(User.id == UUID(admin["id"])).first()
    login_security = LoginSecurityService(db, redis_client)
    login_security.unlock_account(user, admin_user, request.reason)

    return {"message": f"User {user.username} unlocked", "reason": request.reason}


# === 安全事件查询（审计管理员） ===

class SecurityEventInfo(BaseModel):
    id: str
    event_type: str
    severity: str
    source_ip: Optional[str] = None
    user_id: Optional[str] = None
    details: Optional[dict] = None
    action_taken: Optional[str] = None
    resolved: bool
    created_at: datetime


class SecurityEventListResponse(BaseModel):
    events: List[SecurityEventInfo]
    total: int


@router.get("/admin/security-events", response_model=SecurityEventListResponse)
async def list_security_events(
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    resolved: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    admin: dict = Depends(get_admin_user),
    db: Session = Depends(get_db_sync)
):
    """查询安全事件（审计管理员）"""
    query = db.query(SecurityEvent)

    if event_type:
        query = query.filter(SecurityEvent.event_type == event_type)
    if severity:
        query = query.filter(SecurityEvent.severity == severity)
    if resolved is not None:
        query = query.filter(SecurityEvent.resolved == resolved)

    total = query.count()
    events = query.order_by(SecurityEvent.created_at.desc()).offset(offset).limit(limit).all()

    return SecurityEventListResponse(
        events=[
            SecurityEventInfo(
                id=str(e.id),
                event_type=e.event_type,
                severity=e.severity,
                source_ip=e.source_ip,
                user_id=str(e.user_id) if e.user_id else None,
                details=e.details,
                action_taken=e.action_taken,
                resolved=e.resolved,
                created_at=e.created_at
            )
            for e in events
        ],
        total=total
    )


@router.post("/admin/security-events/{event_id}/resolve")
async def resolve_security_event(
    event_id: str,
    admin: dict = Depends(get_admin_user),
    db: Session = Depends(get_db_sync)
):
    """标记安全事件为已解决"""
    event = db.query(SecurityEvent).filter(SecurityEvent.id == UUID(event_id)).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event.resolved = True
    event.resolved_at = datetime.utcnow()
    event.resolved_by = UUID(admin["id"])
    db.commit()

    return {"message": "Event resolved", "event_id": event_id}


# === 密码策略端点 ===

class PasswordPolicyResponse(BaseModel):
    min_length: int
    max_length: int
    require_uppercase: bool
    require_lowercase: bool
    require_digit: bool
    require_special: bool
    special_chars: str
    expire_days: int
    history_size: int
    policy_message: str


@router.get("/password-policy", response_model=PasswordPolicyResponse)
async def get_password_policy():
    """获取密码策略配置"""
    validator = PasswordValidator()

    return PasswordPolicyResponse(
        min_length=validator.MIN_LENGTH,
        max_length=validator.MAX_LENGTH,
        require_uppercase=validator.REQUIRE_UPPERCASE,
        require_lowercase=validator.REQUIRE_LOWERCASE,
        require_digit=validator.REQUIRE_DIGIT,
        require_special=validator.REQUIRE_SPECIAL,
        special_chars=validator.SPECIAL_CHARS,
        expire_days=validator.PASSWORD_EXPIRE_DAYS,
        history_size=validator.PASSWORD_HISTORY_SIZE,
        policy_message=validator.generate_password_policy_message()
    )


class PasswordValidateRequest(BaseModel):
    password: str


class PasswordValidateResponse(BaseModel):
    valid: bool
    errors: List[str]
    strength: str


@router.post("/validate-password", response_model=PasswordValidateResponse)
async def validate_password_strength(
    request: PasswordValidateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db_sync)
):
    """验证密码复杂度"""
    user = db.query(User).filter(User.id == UUID(current_user["id"])).first()
    validator = PasswordValidator()

    result = validator.validate_password(request.password, user)

    return PasswordValidateResponse(
        valid=result["valid"],
        errors=result["errors"],
        strength=result["strength"]
    )


# === 强制修改密码（管理员） ===

@router.post("/admin/force-password-change/{user_id}")
async def force_user_password_change(
    user_id: str,
    admin: dict = Depends(get_admin_user),
    db: Session = Depends(get_db_sync)
):
    """强制用户修改密码"""
    user = db.query(User).filter(User.id == UUID(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.force_password_change = True
    db.commit()

    return {
        "message": f"User {user.username} will be required to change password on next login"
    }