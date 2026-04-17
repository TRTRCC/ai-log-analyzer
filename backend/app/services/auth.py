"""
Authentication Service - JWT-based authentication with RBAC
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from uuid import UUID
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_
from passlib.context import CryptContext

from app.config import settings
from app.models import User, UserRole, Department, AuditLog
from app.utils.security import (
    hash_password,
    verify_password,
    create_jwt_token,
    verify_jwt_token,
    generate_token,
    sanitize_input,
)
from app.utils.logging import get_logger
from app.utils.helpers import generate_uuid

logger = get_logger(__name__)


class AuthService:
    """Authentication and authorization service"""

    pwd_context = CryptContext(
        schemes=["bcrypt"],
        deprecated="auto",
        bcrypt__rounds=settings.password_hash_rounds
    )

    async def authenticate(
        self,
        db_session: AsyncSession,
        username: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Authenticate user with username and password

        Returns:
            Dict with tokens and user info if successful, None otherwise
        """

        # Sanitize input
        username = sanitize_input(username)

        # Find user
        result = await db_session.execute(
            select(User).where(
                and_(
                    User.username == username,
                    User.is_active == True
                )
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            # Log failed attempt
            await self._log_auth_attempt(
                db_session, None, "login_failed", "User not found",
                ip_address, user_agent
            )
            return None

        # Verify password
        if not verify_password(password, user.password_hash):
            await self._log_auth_attempt(
                db_session, str(user.id), "login_failed", "Invalid password",
                ip_address, user_agent
            )
            return None

        # Generate tokens
        access_token = create_jwt_token(
            {"sub": str(user.id), "username": user.username, "role": user.role},
            token_type="access"
        )
        refresh_token = create_jwt_token(
            {"sub": str(user.id)},
            token_type="refresh"
        )

        # Update last login
        await db_session.execute(
            update(User)
            .where(User.id == user.id)
            .values(last_login=datetime.utcnow())
        )

        # Log successful login
        await self._log_auth_attempt(
            db_session, str(user.id), "login_success", "Successful login",
            ip_address, user_agent
        )

        await db_session.commit()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.jwt_expiration_hours * 3600,
            "user": {
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "department_id": str(user.department_id) if user.department_id else None,
            }
        }

    async def refresh_token(
        self,
        db_session: AsyncSession,
        refresh_token: str
    ) -> Optional[Dict[str, str]]:
        """Refresh access token using refresh token"""

        payload = verify_jwt_token(refresh_token, token_type="refresh")
        if not payload:
            return None

        user_id = payload.get("sub")
        if not user_id:
            return None

        # Check if user is still active
        result = await db_session.execute(
            select(User).where(
                and_(
                    User.id == UUID(user_id),
                    User.is_active == True
                )
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            return None

        # Generate new access token
        access_token = create_jwt_token(
            {"sub": str(user.id), "username": user.username, "role": user.role},
            token_type="access"
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.jwt_expiration_hours * 3600
        }

    async def validate_token(
        self,
        db_session: AsyncSession,
        token: str
    ) -> Optional[Dict[str, Any]]:
        """Validate access token and return user info"""

        payload = verify_jwt_token(token, token_type="access")
        if not payload:
            return None

        user_id = payload.get("sub")
        if not user_id:
            return None

        # Get user from database
        result = await db_session.execute(
            select(User).where(User.id == UUID(user_id))
        )
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            return None

        return {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_superuser": user.is_superuser,
            "department_id": str(user.department_id) if user.department_id else None,
        }

    async def logout(
        self,
        db_session: AsyncSession,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """Logout user (log the action)"""
        await self._log_auth_attempt(
            db_session, user_id, "logout", "User logged out",
            ip_address, user_agent
        )
        await db_session.commit()

    async def create_user(
        self,
        db_session: AsyncSession,
        username: str,
        email: str,
        password: str,
        role: UserRole = UserRole.SERVER_USER,
        department_id: Optional[UUID] = None,
        is_superuser: bool = False
    ) -> User:
        """Create new user"""

        # Check if username/email exists
        existing = await db_session.execute(
            select(User).where(
                (User.username == username) | (User.email == email)
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Username or email already exists")

        # Create user
        user = User(
            username=sanitize_input(username),
            email=sanitize_input(email),
            password_hash=hash_password(password),
            role=role,
            department_id=department_id,
            is_active=True,
            is_superuser=is_superuser,
        )

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        logger.info(f"User created: {username} with role {role}")
        return user

    async def update_user(
        self,
        db_session: AsyncSession,
        user_id: UUID,
        **updates
    ) -> Optional[User]:
        """Update user information"""

        result = await db_session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return None

        # Apply updates
        for key, value in updates.items():
            if key == "password":
                user.password_hash = hash_password(value)
            elif key == "email":
                user.email = sanitize_input(value)
            elif key == "username":
                user.username = sanitize_input(value)
            elif hasattr(user, key):
                setattr(user, key, value)

        user.updated_at = datetime.utcnow()
        await db_session.commit()
        await db_session.refresh(user)

        return user

    async def delete_user(
        self,
        db_session: AsyncSession,
        user_id: UUID
    ) -> bool:
        """Delete (deactivate) user"""

        result = await db_session.execute(
            update(User)
            .where(User.id == user_id)
            .values(is_active=False, updated_at=datetime.utcnow())
        )
        await db_session.commit()

        return result.rowcount > 0

    async def get_user(
        self,
        db_session: AsyncSession,
        user_id: UUID
    ) -> Optional[User]:
        """Get user by ID"""

        result = await db_session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_users(
        self,
        db_session: AsyncSession,
        role: Optional[UserRole] = None,
        department_id: Optional[UUID] = None,
        is_active: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[User]:
        """Get users with filters"""

        query = select(User)

        if role:
            query = query.where(User.role == role)
        if department_id:
            query = query.where(User.department_id == department_id)
        if is_active is not None:
            query = query.where(User.is_active == is_active)

        query = query.limit(limit).offset(offset).order_by(User.created_at.desc())

        result = await db_session.execute(query)
        return list(result.scalars().all())

    async def change_password(
        self,
        db_session: AsyncSession,
        user_id: UUID,
        current_password: str,
        new_password: str
    ) -> bool:
        """Change user password"""

        result = await db_session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return False

        # Verify current password
        if not verify_password(current_password, user.password_hash):
            return False

        # Update password
        user.password_hash = hash_password(new_password)
        user.updated_at = datetime.utcnow()
        await db_session.commit()

        return True

    async def reset_password(
        self,
        db_session: AsyncSession,
        user_id: UUID,
        new_password: Optional[str] = None
    ) -> Optional[str]:
        """Reset user password (admin operation)"""

        result = await db_session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return None

        # Generate new password if not provided
        if not new_password:
            new_password = generate_token(16)

        user.password_hash = hash_password(new_password)
        user.updated_at = datetime.utcnow()
        await db_session.commit()

        return new_password

    def check_permission(
        self,
        user: User,
        permission: str
    ) -> bool:
        """Check if user has specific permission"""

        # Super admin has all permissions
        if user.role == UserRole.SUPER_ADMIN or user.is_superuser:
            return True

        # Define role permissions
        role_permissions = {
            UserRole.AUDIT_ADMIN: [
                "log:all:read",
                "report:all:read",
                "audit:view",
                "ai:usage:view",
            ],
            UserRole.DEPT_ADMIN: [
                "user:dept:manage",
                "log:dept:read",
                "report:dept:read",
            ],
            UserRole.NETWORK_USER: [
                "log:network:read",
                "report:own:read",
                "ai:manual:run",
            ],
            UserRole.SERVER_USER: [
                "log:server:read",
                "report:own:read",
                "ai:manual:run",
            ],
            UserRole.K8S_USER: [
                "log:k8s:read",
                "report:own:read",
                "ai:manual:run",
            ],
        }

        user_permissions = role_permissions.get(user.role, [])
        return permission in user_permissions

    def can_access_log_type(
        self,
        user: User,
        log_type: str
    ) -> bool:
        """Check if user can access specific log type"""

        if user.role == UserRole.SUPER_ADMIN or user.role == UserRole.AUDIT_ADMIN:
            return True

        access_map = {
            UserRole.NETWORK_USER: ["network"],
            UserRole.SERVER_USER: ["server"],
            UserRole.K8S_USER: ["k8s"],
        }

        allowed_types = access_map.get(user.role, [])
        return log_type in allowed_types

    async def _log_auth_attempt(
        self,
        db_session: AsyncSession,
        user_id: Optional[str],
        action: str,
        details: str,
        ip_address: Optional[str],
        user_agent: Optional[str]
    ):
        """Log authentication attempt"""

        log = AuditLog(
            user_id=UUID(user_id) if user_id else None,
            action=action,
            resource_type="auth",
            details=json.dumps({"message": details}),
            ip_address=ip_address,
            user_agent=user_agent
        )
        db_session.add(log)


class RoleService:
    """Role and permission management"""

    ROLE_INFO = {
        UserRole.SUPER_ADMIN: {
            "name": "Super Administrator",
            "description": "Full system access and configuration",
            "permissions": ["*"]
        },
        UserRole.AUDIT_ADMIN: {
            "name": "Audit Administrator",
            "description": "View all logs and audit information",
            "permissions": ["log:all:read", "report:all:read", "audit:view", "ai:usage:view"]
        },
        UserRole.DEPT_ADMIN: {
            "name": "Department Administrator",
            "description": "Manage department users and logs",
            "permissions": ["user:dept:manage", "log:dept:read", "report:dept:read"]
        },
        UserRole.NETWORK_USER: {
            "name": "Network Team User",
            "description": "Access network device logs only",
            "permissions": ["log:network:read", "report:own:read", "ai:manual:run"]
        },
        UserRole.SERVER_USER: {
            "name": "Server Team User",
            "description": "Access server logs only",
            "permissions": ["log:server:read", "report:own:read", "ai:manual:run"]
        },
        UserRole.K8S_USER: {
            "name": "Kubernetes Team User",
            "description": "Access K8S logs only",
            "permissions": ["log:k8s:read", "report:own:read", "ai:manual:run"]
        },
    }

    def get_role_info(self, role: UserRole) -> Dict[str, Any]:
        """Get role information"""
        return self.ROLE_INFO.get(role, {})

    def get_all_roles(self) -> List[Dict[str, Any]]:
        """Get all available roles"""
        return [
            {
                "role": role.value,
                **info
            }
            for role, info in self.ROLE_INFO.items()
        ]

    def get_users_by_role(self, role: UserRole) -> str:
        """Get user count for role"""
        # This would query database in real implementation
        return "0"


class DepartmentService:
    """Department management"""

    async def create_department(
        self,
        db_session: AsyncSession,
        name: str,
        description: Optional[str] = None
    ) -> Department:
        """Create new department"""

        dept = Department(
            name=sanitize_input(name),
            description=description
        )
        db_session.add(dept)
        await db_session.commit()
        await db_session.refresh(dept)

        return dept

    async def get_departments(
        self,
        db_session: AsyncSession
    ) -> List[Department]:
        """Get all departments"""

        result = await db_session.execute(
            select(Department).order_by(Department.name)
        )
        return list(result.scalars().all())


# Global service instances
auth_service = AuthService()
role_service = RoleService()
department_service = DepartmentService()


async def get_auth_service() -> AuthService:
    return auth_service

async def get_role_service() -> RoleService:
    return role_service

async def get_department_service() -> DepartmentService:
    return department_service