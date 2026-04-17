"""
Authentication API Routes
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.models import UserRole
from app.services.auth import auth_service, get_auth_service, AuthService
from app.utils.security import sanitize_input

router = APIRouter()
security = HTTPBearer()


# Request/Response models
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)
    role: str = "server_user"
    department_id: Optional[str] = None


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    department_id: Optional[str] = None
    is_active: Optional[bool] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)


class UserInfo(BaseModel):
    id: str
    username: str
    email: str
    role: str
    department_id: Optional[str] = None
    is_active: bool
    last_login: Optional[datetime] = None
    created_at: datetime


# Dependencies
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db_session)
) -> dict:
    """Get current authenticated user"""

    user_info = await auth_service.validate_token(db, credentials.credentials)

    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    return user_info


async def get_admin_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Require admin role"""

    if current_user["role"] not in ["super_admin", "audit_admin", "dept_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    return current_user


async def get_super_admin(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Require super admin role"""

    if current_user["role"] != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required"
        )

    return current_user


# Routes
@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
    req: Request = None
):
    """Login with username and password"""

    ip_address = req.client.host if req else None
    user_agent = req.headers.get("user-agent") if req else None

    result = await auth_service.authenticate(
        db,
        request.username,
        request.password,
        ip_address,
        user_agent
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    return result


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db_session)
):
    """Refresh access token"""

    result = await auth_service.refresh_token(db, request.refresh_token)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    return result


@router.post("/logout")
async def logout(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
    req: Request = None
):
    """Logout current user"""

    ip_address = req.client.host if req else None
    user_agent = req.headers.get("user-agent") if req else None

    await auth_service.logout(db, current_user["id"], ip_address, user_agent)

    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get current user information"""

    user = await auth_service.get_user(db, UUID(current_user["id"]))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserInfo(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role,
        department_id=str(user.department_id) if user.department_id else None,
        is_active=user.is_active,
        last_login=user.last_login,
        created_at=user.created_at
    )


@router.post("/change-password")
async def change_password(
    request: PasswordChange,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Change current user password"""

    success = await auth_service.change_password(
        db,
        UUID(current_user["id"]),
        request.current_password,
        request.new_password
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    return {"message": "Password changed successfully"}


# User management (admin)
@router.post("/users", response_model=UserInfo)
async def create_user(
    request: UserCreate,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Create new user (admin only)"""

    try:
        role = UserRole(request.role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {request.role}"
        )

    department_id = UUID(request.department_id) if request.department_id else None

    try:
        user = await auth_service.create_user(
            db,
            request.username,
            request.email,
            request.password,
            role,
            department_id
        )

        return UserInfo(
            id=str(user.id),
            username=user.username,
            email=user.email,
            role=user.role,
            department_id=str(user.department_id) if user.department_id else None,
            is_active=user.is_active,
            last_login=user.last_login,
            created_at=user.created_at
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/users", response_model=list[UserInfo])
async def list_users(
    role: Optional[str] = None,
    department_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db_session)
):
    """List users (admin only)"""

    role_enum = UserRole(role) if role else None
    dept_uuid = UUID(department_id) if department_id else None

    users = await auth_service.get_users(
        db,
        role=role_enum,
        department_id=dept_uuid,
        is_active=is_active,
        limit=limit,
        offset=offset
    )

    return [
        UserInfo(
            id=str(u.id),
            username=u.username,
            email=u.email,
            role=u.role,
            department_id=str(u.department_id) if u.department_id else None,
            is_active=u.is_active,
            last_login=u.last_login,
            created_at=u.created_at
        )
        for u in users
    ]


@router.get("/users/{user_id}", response_model=UserInfo)
async def get_user(
    user_id: str,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get user by ID (admin only)"""

    user = await auth_service.get_user(db, UUID(user_id))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserInfo(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role,
        department_id=str(user.department_id) if user.department_id else None,
        is_active=user.is_active,
        last_login=user.last_login,
        created_at=user.created_at
    )


@router.put("/users/{user_id}", response_model=UserInfo)
async def update_user(
    user_id: str,
    request: UserUpdate,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Update user (admin only)"""

    updates = {}

    if request.email:
        updates["email"] = request.email
    if request.role:
        updates["role"] = UserRole(request.role)
    if request.department_id:
        updates["department_id"] = UUID(request.department_id)
    if request.is_active is not None:
        updates["is_active"] = request.is_active

    user = await auth_service.update_user(db, UUID(user_id), **updates)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return UserInfo(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role,
        department_id=str(user.department_id) if user.department_id else None,
        is_active=user.is_active,
        last_login=user.last_login,
        created_at=user.created_at
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Delete (deactivate) user (admin only)"""

    success = await auth_service.delete_user(db, UUID(user_id))

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return {"message": "User deactivated successfully"}


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    admin: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Reset user password (admin only)"""

    new_password = await auth_service.reset_password(db, UUID(user_id))

    if not new_password:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return {
        "message": "Password reset successfully",
        "new_password": new_password  # In production, send via email
    }


@router.get("/roles")
async def list_roles():
    """List all available roles"""

    from app.services.auth import role_service
    return role_service.get_all_roles()