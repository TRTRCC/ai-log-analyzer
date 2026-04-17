"""
Backup and Recovery API Routes - 等保三备份管理
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db_sync
from app.api.auth import get_super_admin, get_admin_user
from app.services.backup_service import BackupService
from app.services.audit_tamper_proof import AuditLogTamperProofService

router = APIRouter()
security = HTTPBearer()


class BackupInfo(BaseModel):
    name: str
    timestamp: str
    type: str
    checksum: str
    size_bytes: int
    components: dict
    file_path: str


class BackupListResponse(BaseModel):
    backups: List[BackupInfo]
    total: int


class BackupCreateResponse(BaseModel):
    name: str
    path: str
    checksum: str
    size_bytes: int
    components: dict


class BackupRestoreResponse(BaseModel):
    success: bool
    backup_name: str
    results: dict


class BackupVerifyResponse(BaseModel):
    valid: bool
    backup_name: Optional[str] = None
    components: Optional[List[str]] = None
    error: Optional[str] = None


class CleanupResponse(BaseModel):
    deleted_count: int
    deleted_files: List[str]


class AuditVerificationReport(BaseModel):
    total_logs: int
    last_sequence: int
    recent_verification: dict
    chain_integrity: bool
    checked_range: int


# === 备份管理端点 ===

@router.post("/create", response_model=BackupCreateResponse)
async def create_backup(
    backup_type: str = "full",
    admin: dict = Depends(get_super_admin),
    db: Session = Depends(get_db_sync)
):
    """创建备份（超级管理员）"""
    backup_service = BackupService(db)

    result = backup_service.create_backup(backup_type)

    if result.get("components", {}).get("postgresql", {}).get("status") == "failed":
        raise HTTPException(
            status_code=500,
            detail="Backup creation failed"
        )

    return BackupCreateResponse(
        name=result["name"],
        path=result["path"],
        checksum=result["checksum"],
        size_bytes=result["size_bytes"],
        components=result["components"]
    )


@router.get("/list", response_model=BackupListResponse)
async def list_backups(
    admin: dict = Depends(get_admin_user),
    db: Session = Depends(get_db_sync)
):
    """列出所有备份（管理员）"""
    backup_service = BackupService(db)
    backups = backup_service.list_backups()

    return BackupListResponse(
        backups=[
            BackupInfo(
                name=b.get("name", ""),
                timestamp=b.get("timestamp", ""),
                type=b.get("type", ""),
                checksum=b.get("checksum", ""),
                size_bytes=b.get("file_size", 0),
                components=b.get("components", {}),
                file_path=b.get("file_path", "")
            )
            for b in backups
        ],
        total=len(backups)
    )


@router.post("/restore/{backup_name}", response_model=BackupRestoreResponse)
async def restore_backup(
    backup_name: str,
    admin: dict = Depends(get_super_admin),
    db: Session = Depends(get_db_sync)
):
    """恢复备份（超级管理员）"""
    backup_service = BackupService(db)

    result = backup_service.restore_backup(backup_name)

    if not result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=result.get("error", "Restore failed")
        )

    return BackupRestoreResponse(
        success=result["success"],
        backup_name=result["backup_name"],
        results=result["results"]
    )


@router.get("/verify/{backup_name}", response_model=BackupVerifyResponse)
async def verify_backup(
    backup_name: str,
    admin: dict = Depends(get_admin_user),
    db: Session = Depends(get_db_sync)
):
    """验证备份完整性（管理员）"""
    backup_service = BackupService(db)

    result = backup_service.verify_backup(backup_name)

    return BackupVerifyResponse(
        valid=result["valid"],
        backup_name=result.get("backup_name"),
        components=result.get("components"),
        error=result.get("error")
    )


@router.post("/cleanup", response_model=CleanupResponse)
async def cleanup_old_backups(
    admin: dict = Depends(get_super_admin),
    db: Session = Depends(get_db_sync)
):
    """清理过期备份（超级管理员）"""
    backup_service = BackupService(db)

    result = backup_service.cleanup_old_backups()

    return CleanupResponse(
        deleted_count=result["deleted_count"],
        deleted_files=result["deleted_files"]
    )


# === 审计日志验证端点 ===

@router.get("/audit/verify", response_model=AuditVerificationReport)
async def verify_audit_log_chain(
    admin: dict = Depends(get_admin_user),
    db: Session = Depends(get_db_sync)
):
    """验证审计日志链完整性（审计管理员）"""
    audit_service = AuditLogTamperProofService(db)

    report = audit_service.get_verification_report()

    return AuditVerificationReport(
        total_logs=report["total_logs"],
        last_sequence=report["last_sequence"],
        recent_verification=report["recent_verification"],
        chain_integrity=report["chain_integrity"],
        checked_range=report["checked_range"]
    )


@router.get("/audit/export-key")
async def export_audit_public_key(
    admin: dict = Depends(get_super_admin),
    db: Session = Depends(get_db_sync)
):
    """导出审计日志公钥（超级管理员）"""
    audit_service = AuditLogTamperProofService(db)

    public_key = audit_service.export_public_key()

    return {
        "public_key": public_key,
        "purpose": "用于外部验证审计日志签名"
    }


@router.get("/audit/verify-range")
async def verify_audit_log_range(
    start_seq: int = 1,
    end_seq: int = 100,
    admin: dict = Depends(get_admin_user),
    db: Session = Depends(get_db_sync)
):
    """验证指定范围的审计日志"""
    audit_service = AuditLogTamperProofService(db)

    result = audit_service.verify_log_chain(start_seq, end_seq)

    return {
        "valid": result["valid"],
        "checked": result["checked"],
        "errors": result["errors"]
    }