"""
Auto Backup and Recovery Service - 等保三自动备份与恢复
"""

import os
import json
import shutil
import gzip
import tarfile
from datetime import datetime, timedelta
from typing import Optional, List
from pathlib import Path
import subprocess
import hashlib

from sqlalchemy.orm import Session
from app.config import settings


class BackupService:
    """自动备份服务"""

    # 等保三备份配置
    BACKUP_DIR = Path(settings.data_dir) / "backups"
    RETENTION_DAYS = 30  # 保留30天
    BACKUP_INTERVAL_HOURS = 24  # 每24小时备份
    MAX_BACKUPS = 30  # 最大保留数量

    def __init__(self, db: Session):
        self.db = db
        self.backup_dir = self.BACKUP_DIR
        self._ensure_backup_dir()

    def _ensure_backup_dir(self):
        """确保备份目录存在"""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        # 等保三：设置目录权限
        os.chmod(self.backup_dir, 0o700)

    def create_backup(self, backup_type: str = "full") -> dict:
        """创建备份"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{backup_type}_{timestamp}"
        backup_path = self.backup_dir / backup_name

        # 创建备份目录
        backup_path.mkdir(parents=True, exist_ok=True)

        # 备份PostgreSQL
        pg_backup = self._backup_postgresql(backup_path)

        # 备份ClickHouse
        ch_backup = self._backup_clickhouse(backup_path)

        # 备份配置文件
        config_backup = self._backup_config(backup_path)

        # 备份审计日志
        audit_backup = self._backup_audit_logs(backup_path)

        # 创建备份元数据
        metadata = {
            "name": backup_name,
            "type": backup_type,
            "timestamp": timestamp,
            "created_at": datetime.utcnow().isoformat(),
            "components": {
                "postgresql": pg_backup,
                "clickhouse": ch_backup,
                "config": config_backup,
                "audit_logs": audit_backup
            }
        }

        # 写入元数据文件
        metadata_path = backup_path / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        # 计算备份校验码
        checksum = self._calculate_checksum(backup_path)
        metadata["checksum"] = checksum
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        # 压缩备份
        compressed_path = self._compress_backup(backup_path)

        # 清理临时目录
        shutil.rmtree(backup_path)

        # 记录备份日志
        self._log_backup(metadata)

        return {
            "name": backup_name,
            "path": str(compressed_path),
            "checksum": checksum,
            "size_bytes": compressed_path.stat().st_size,
            "components": metadata["components"]
        }

    def _backup_postgresql(self, backup_path: Path) -> dict:
        """备份PostgreSQL数据库"""
        pg_dir = backup_path / "postgresql"
        pg_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 使用pg_dump导出
            db_name = settings.database_url.split('/')[-1]
            dump_file = pg_dir / "database.sql.gz"

            # 执行pg_dump（通过docker）
            result = subprocess.run(
                [
                    "docker", "exec", "postgres",
                    "pg_dump", "-U", "ailoguser", db_name
                ],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                # 压缩存储
                with gzip.open(dump_file, 'wt') as f:
                    f.write(result.stdout)

                return {
                    "status": "success",
                    "file": str(dump_file),
                    "size_bytes": dump_file.stat().st_size
                }
            else:
                return {
                    "status": "failed",
                    "error": result.stderr
                }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e)
            }

    def _backup_clickhouse(self, backup_path: Path) -> dict:
        """备份ClickHouse数据库"""
        ch_dir = backup_path / "clickhouse"
        ch_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 使用clickhouse-client导出
            dump_file = ch_dir / "logs_backup.sql.gz"

            result = subprocess.run(
                [
                    "docker", "exec", "clickhouse",
                    "clickhouse-client",
                    "--query", "BACKUP DATABASE ailoganalyzer_logs"
                ],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                with gzip.open(dump_file, 'wt') as f:
                    f.write(result.stdout)

                return {
                    "status": "success",
                    "file": str(dump_file),
                    "size_bytes": dump_file.stat().st_size
                }
            else:
                # 备用方案：导出表数据
                tables = ["logs", "log_fingerprints"]
                exported_tables = []
                for table in tables:
                    table_file = ch_dir / f"{table}.csv.gz"
                    result = subprocess.run(
                        [
                            "docker", "exec", "clickhouse",
                            "clickhouse-client",
                            "--query", f"SELECT * FROM {table} FORMAT CSV"
                        ],
                        capture_output=True,
                        text=True
                    )
                    if result.returncode == 0:
                        with gzip.open(table_file, 'wt') as f:
                            f.write(result.stdout)
                        exported_tables.append(table)

                if exported_tables:
                    return {
                        "status": "partial",
                        "tables": exported_tables
                    }
                return {
                    "status": "failed",
                    "error": result.stderr
                }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e)
            }

    def _backup_config(self, backup_path: Path) -> dict:
        """备份配置文件"""
        config_dir = backup_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 备份.env文件（加密存储）
            env_file = Path(settings.project_dir) / ".env"
            if env_file.exists():
                # 备份时加密敏感信息
                encrypted_env = self._encrypt_env_file(env_file)
                target_file = config_dir / ".env.enc"
                with open(target_file, 'w') as f:
                    f.write(encrypted_env)

            return {
                "status": "success",
                "files": ["env_encrypted"]
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e)
            }

    def _backup_audit_logs(self, backup_path: Path) -> dict:
        """备份审计日志"""
        audit_dir = backup_path / "audit_logs"
        audit_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 导出审计日志
            from app.models.user import AuditLog
            logs = self.db.query(AuditLog).order_by(AuditLog.sequence_number).all()

            log_file = audit_dir / "audit_logs.json.gz"
            logs_data = [
                {
                    "id": str(log.id),
                    "user_id": str(log.user_id) if log.user_id else None,
                    "action": log.action,
                    "resource_type": log.resource_type,
                    "resource_id": str(log.resource_id) if log.resource_id else None,
                    "details": log.details,
                    "ip_address": log.ip_address,
                    "user_agent": log.user_agent,
                    "created_at": log.created_at.isoformat(),
                    "log_hash": log.log_hash,
                    "prev_hash": log.prev_hash,
                    "signature": log.signature,
                    "sequence_number": log.sequence_number
                }
                for log in logs
            ]

            with gzip.open(log_file, 'wt') as f:
                json.dump(logs_data, f)

            return {
                "status": "success",
                "count": len(logs),
                "file": str(log_file),
                "size_bytes": log_file.stat().st_size
            }
        except Exception as e:
            return {
                "status": "failed",
                "error": str(e)
            }

    def _calculate_checksum(self, backup_path: Path) -> str:
        """计算备份校验码"""
        hasher = hashlib.sha256()

        for file_path in backup_path.rglob('*'):
            if file_path.is_file():
                with open(file_path, 'rb') as f:
                    while chunk := f.read(8192):
                        hasher.update(chunk)

        return hasher.hexdigest()

    def _compress_backup(self, backup_path: Path) -> Path:
        """压缩备份"""
        compressed_file = backup_path.with_suffix('.tar.gz')

        with tarfile.open(compressed_file, 'w:gz') as tar:
            tar.add(backup_path, arcname=backup_path.name)

        return compressed_file

    def _encrypt_env_file(self, env_file: Path) -> str:
        """加密配置文件"""
        from cryptography.fernet import Fernet
        key = settings.backup_encryption_key
        fernet = Fernet(key)

        with open(env_file, 'r') as f:
            content = f.read()

        return fernet.encrypt(content.encode()).decode()

    def _log_backup(self, metadata: dict):
        """记录备份日志"""
        from app.services.audit_tamper_proof import AuditLogTamperProofService
        audit_service = AuditLogTamperProofService(self.db)
        audit_service.create_audit_log(
            user_id=None,
            action="backup_created",
            resource_type="backup",
            details=metadata
        )

    def list_backups(self) -> List[dict]:
        """列出所有备份"""
        backups = []

        for backup_file in self.backup_dir.glob("backup_*.tar.gz"):
            # 解压读取元数据
            try:
                with tarfile.open(backup_file, 'r:gz') as tar:
                    metadata_member = None
                    for member in tar.getmembers():
                        if member.name.endswith('metadata.json'):
                            metadata_member = member
                            break

                    if metadata_member:
                        f = tar.extractfile(metadata_member)
                        metadata = json.load(f)
                        metadata['file_path'] = str(backup_file)
                        metadata['file_size'] = backup_file.stat().st_size
                        backups.append(metadata)
            except Exception:
                backups.append({
                    "name": backup_file.name,
                    "file_path": str(backup_file),
                    "error": "metadata_read_failed"
                })

        return sorted(backups, key=lambda x: x.get('timestamp', ''), reverse=True)

    def restore_backup(self, backup_name: str) -> dict:
        """恢复备份"""
        backup_file = self.backup_dir / f"{backup_name}.tar.gz"

        if not backup_file.exists():
            return {
                "success": False,
                "error": "Backup not found"
            }

        # 解压备份
        extract_dir = self.backup_dir / "restore_temp"
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            with tarfile.open(backup_file, 'r:gz') as tar:
                tar.extractall(extract_dir)

            # 查找备份目录
            backup_content = None
            for item in extract_dir.iterdir():
                if item.is_dir() and item.name.startswith('backup_'):
                    backup_content = item
                    break

            if not backup_content:
                return {
                    "success": False,
                    "error": "Backup content not found"
                }

            # 验证校验码
            metadata_file = backup_content / "metadata.json"
            if metadata_file.exists():
                metadata = json.load(open(metadata_file))
                computed_checksum = self._calculate_checksum(backup_content)
                if computed_checksum != metadata.get('checksum'):
                    return {
                        "success": False,
                        "error": "Checksum verification failed"
                    }

            # 恢复PostgreSQL
            pg_result = self._restore_postgresql(backup_content / "postgresql")

            # 恢复ClickHouse
            ch_result = self._restore_clickhouse(backup_content / "clickhouse")

            # 恢复审计日志
            audit_result = self._restore_audit_logs(backup_content / "audit_logs")

            # 清理临时目录
            shutil.rmtree(extract_dir)

            # 记录恢复日志
            from app.services.audit_tamper_proof import AuditLogTamperProofService
            audit_service = AuditLogTamperProofService(self.db)
            audit_service.create_audit_log(
                user_id=None,
                action="backup_restored",
                resource_type="backup",
                resource_id=backup_name,
                details={
                    "postgresql": pg_result,
                    "clickhouse": ch_result,
                    "audit_logs": audit_result
                }
            )

            return {
                "success": True,
                "backup_name": backup_name,
                "results": {
                    "postgresql": pg_result,
                    "clickhouse": ch_result,
                    "audit_logs": audit_result
                }
            }

        except Exception as e:
            shutil.rmtree(extract_dir, ignore_errors=True)
            return {
                "success": False,
                "error": str(e)
            }

    def _restore_postgresql(self, pg_dir: Path) -> dict:
        """恢复PostgreSQL"""
        if not pg_dir.exists():
            return {"status": "skipped", "reason": "no_backup"}

        dump_file = pg_dir / "database.sql.gz"
        if not dump_file.exists():
            return {"status": "skipped", "reason": "no_dump_file"}

        try:
            with gzip.open(dump_file, 'rt') as f:
                sql_content = f.read()

            result = subprocess.run(
                [
                    "docker", "exec", "-i", "postgres",
                    "psql", "-U", "ailoguser", "ailoganalyzer"
                ],
                input=sql_content,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                return {"status": "success"}
            return {"status": "failed", "error": result.stderr}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def _restore_clickhouse(self, ch_dir: Path) -> dict:
        """恢复ClickHouse"""
        if not ch_dir.exists():
            return {"status": "skipped", "reason": "no_backup"}

        # 恢复CSV文件
        for table_file in ch_dir.glob("*.csv.gz"):
            table_name = table_file.name.replace('.csv.gz', '')
            try:
                with gzip.open(table_file, 'rt') as f:
                    csv_content = f.read()

                # 通过clickhouse-client导入
                result = subprocess.run(
                    [
                        "docker", "exec", "-i", "clickhouse",
                        "clickhouse-client",
                        "--query", f"INSERT INTO {table_name} FORMAT CSV"
                    ],
                    input=csv_content,
                    capture_output=True,
                    text=True
                )

                if result.returncode != 0:
                    return {"status": "failed", "table": table_name, "error": result.stderr}
            except Exception as e:
                return {"status": "failed", "error": str(e)}

        return {"status": "success"}

    def _restore_audit_logs(self, audit_dir: Path) -> dict:
        """恢复审计日志"""
        log_file = audit_dir / "audit_logs.json.gz"
        if not log_file.exists():
            return {"status": "skipped", "reason": "no_backup"}

        try:
            with gzip.open(log_file, 'rt') as f:
                logs_data = json.load(f)

            # 清空现有日志并恢复
            from app.models.user import AuditLog
            self.db.query(AuditLog).delete()

            for log_entry in logs_data:
                log = AuditLog(
                    id=log_entry['id'],
                    user_id=log_entry['user_id'],
                    action=log_entry['action'],
                    resource_type=log_entry['resource_type'],
                    resource_id=log_entry['resource_id'],
                    details=log_entry['details'],
                    ip_address=log_entry['ip_address'],
                    user_agent=log_entry['user_agent'],
                    created_at=datetime.fromisoformat(log_entry['created_at']),
                    log_hash=log_entry['log_hash'],
                    prev_hash=log_entry['prev_hash'],
                    signature=log_entry['signature'],
                    sequence_number=log_entry['sequence_number']
                )
                self.db.add(log)

            self.db.commit()
            return {"status": "success", "count": len(logs_data)}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def cleanup_old_backups(self) -> dict:
        """清理过期备份"""
        now = datetime.utcnow()
        deleted = []

        for backup_file in self.backup_dir.glob("backup_*.tar.gz"):
            # 检查备份时间
            file_mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
            age_days = (now - file_mtime).days

            if age_days > self.RETENTION_DAYS:
                backup_file.unlink()
                deleted.append(backup_file.name)

        return {
            "deleted_count": len(deleted),
            "deleted_files": deleted
        }

    def verify_backup(self, backup_name: str) -> dict:
        """验证备份完整性"""
        backup_file = self.backup_dir / f"{backup_name}.tar.gz"

        if not backup_file.exists():
            return {"valid": False, "error": "Backup not found"}

        try:
            with tarfile.open(backup_file, 'r:gz') as tar:
                # 检查必需文件
                required_files = ['metadata.json', 'postgresql/', 'audit_logs/']
                found_files = [m.name for m in tar.getmembers()]

                missing = []
                for required in required_files:
                    if not any(f.startswith(required) for f in found_files):
                        missing.append(required)

                if missing:
                    return {
                        "valid": False,
                        "error": "Missing components",
                        "missing": missing
                    }

                # 验证校验码
                # 需要解压验证...

                return {
                    "valid": True,
                    "backup_name": backup_name,
                    "components": found_files
                }
        except Exception as e:
            return {"valid": False, "error": str(e)}