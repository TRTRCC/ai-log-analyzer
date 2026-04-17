"""
Audit Log Tamper-Proof Service - 等保三审计日志防篡改
"""

import hashlib
import json
from datetime import datetime
from typing import Optional, List
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
import base64

from app.models.user import AuditLog
from sqlalchemy.orm import Session


class AuditLogTamperProofService:
    """审计日志防篡改服务 - 链式哈希 + RSA签名"""

    # RSA密钥配置（生产环境应从安全存储加载）
    _private_key = None
    _public_key = None

    def __init__(self, db: Session):
        self.db = db
        self._init_keys()

    def _init_keys(self):
        """初始化RSA密钥"""
        # 生产环境应从安全配置加载
        if self._private_key is None:
            self._private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            self._public_key = self._private_key.public_key()

    def create_audit_log(
        self,
        user_id: Optional[str],
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuditLog:
        """创建防篡改审计日志"""
        # 获取前一条日志的哈希
        prev_log = self.db.query(AuditLog).order_by(AuditLog.sequence_number.desc()).first()
        prev_hash = prev_log.log_hash if prev_log else self._get_initial_hash()
        sequence_number = prev_log.sequence_number + 1 if prev_log else 1

        # 计算当前日志内容哈希
        content = self._build_log_content(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            prev_hash=prev_hash,
            sequence_number=sequence_number
        )

        log_hash = self._compute_hash(content)

        # RSA签名
        signature = self._sign_log(log_hash)

        # 创建日志记录
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(details) if details else None,
            ip_address=ip_address,
            user_agent=user_agent,
            log_hash=log_hash,
            prev_hash=prev_hash,
            signature=signature,
            sequence_number=sequence_number
        )

        self.db.add(audit_log)
        self.db.commit()

        return audit_log

    def _build_log_content(
        self,
        user_id: Optional[str],
        action: str,
        resource_type: Optional[str],
        resource_id: Optional[str],
        details: Optional[dict],
        ip_address: Optional[str],
        user_agent: Optional[str],
        prev_hash: str,
        sequence_number: int
    ) -> str:
        """构建日志内容（用于哈希）"""
        content = json.dumps({
            "user_id": str(user_id) if user_id else None,
            "action": action,
            "resource_type": resource_type,
            "resource_id": str(resource_id) if resource_id else None,
            "details": details,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "timestamp": datetime.utcnow().isoformat(),
            "prev_hash": prev_hash,
            "sequence_number": sequence_number
        }, sort_keys=True)
        return content

    def _compute_hash(self, content: str) -> str:
        """计算SHA256哈希"""
        return hashlib.sha256(content.encode()).hexdigest()

    def _get_initial_hash(self) -> str:
        """初始哈希（第一条日志的前置哈希）"""
        return "0000000000000000000000000000000000000000000000000000000000000000"

    def _sign_log(self, log_hash: str) -> str:
        """RSA签名"""
        signature = self._private_key.sign(
            log_hash.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return base64.b64encode(signature).decode()

    def verify_log_chain(self, start_seq: int = None, end_seq: int = None) -> dict:
        """验证日志链完整性"""
        query = self.db.query(AuditLog).order_by(AuditLog.sequence_number.asc())

        if start_seq:
            query = query.filter(AuditLog.sequence_number >= start_seq)
        if end_seq:
            query = query.filter(AuditLog.sequence_number <= end_seq)

        logs = query.all()

        if not logs:
            return {"valid": True, "checked": 0, "errors": []}

        errors = []
        prev_hash = self._get_initial_hash()

        for log in logs:
            # 验证前置哈希链接
            if log.prev_hash != prev_hash:
                errors.append({
                    "sequence": log.sequence_number,
                    "error": "chain_broken",
                    "expected_prev": prev_hash,
                    "actual_prev": log.prev_hash
                })

            # 验证内容哈希
            content = self._build_log_content(
                user_id=str(log.user_id) if log.user_id else None,
                action=log.action,
                resource_type=log.resource_type,
                resource_id=str(log.resource_id) if log.resource_id else None,
                details=json.loads(log.details) if log.details else None,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                prev_hash=log.prev_hash,
                sequence_number=log.sequence_number
            )
            computed_hash = self._compute_hash(content)

            if computed_hash != log.log_hash:
                errors.append({
                    "sequence": log.sequence_number,
                    "error": "hash_mismatch",
                    "computed": computed_hash,
                    "stored": log.log_hash
                })

            # 验证签名
            if not self._verify_signature(log.log_hash, log.signature):
                errors.append({
                    "sequence": log.sequence_number,
                    "error": "signature_invalid"
                })

            prev_hash = log.log_hash

        return {
            "valid": len(errors) == 0,
            "checked": len(logs),
            "errors": errors
        }

    def _verify_signature(self, log_hash: str, signature: str) -> bool:
        """验证RSA签名"""
        try:
            sig_bytes = base64.b64decode(signature)
            self._public_key.verify(
                sig_bytes,
                log_hash.encode(),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return True
        except Exception:
            return False

    def verify_single_log(self, log: AuditLog) -> dict:
        """验证单条日志"""
        errors = []

        # 验证前置哈希链接
        if log.sequence_number > 1:
            prev_log = self.db.query(AuditLog).filter(
                AuditLog.sequence_number == log.sequence_number - 1
            ).first()
            if prev_log and log.prev_hash != prev_log.log_hash:
                errors.append("prev_hash_link_broken")

        # 验证内容哈希
        content = self._build_log_content(
            user_id=str(log.user_id) if log.user_id else None,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=str(log.resource_id) if log.resource_id else None,
            details=json.loads(log.details) if log.details else None,
            ip_address=log.ip_address,
            user_agent=log.user_agent,
            prev_hash=log.prev_hash,
            sequence_number=log.sequence_number
        )
        computed_hash = self._compute_hash(content)

        if computed_hash != log.log_hash:
            errors.append("hash_mismatch")

        # 验证签名
        if not self._verify_signature(log.log_hash, log.signature):
            errors.append("signature_invalid")

        return {
            "valid": len(errors) == 0,
            "sequence": log.sequence_number,
            "errors": errors
        }

    def get_verification_report(self) -> dict:
        """获取完整性验证报告"""
        total_logs = self.db.query(AuditLog).count()
        last_log = self.db.query(AuditLog).order_by(AuditLog.sequence_number.desc()).first()

        # 验证最近100条日志
        result = self.verify_log_chain(
            start_seq=max(1, (last_log.sequence_number - 100) if last_log else 1)
        )

        return {
            "total_logs": total_logs,
            "last_sequence": last_log.sequence_number if last_log else 0,
            "recent_verification": result,
            "chain_integrity": result["valid"],
            "checked_range": 100
        }

    def export_public_key(self) -> str:
        """导出公钥（用于外部验证）"""
        pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return pem.decode()


class AuditLogQueryService:
    """审计日志查询服务"""

    def __init__(self, db: Session):
        self.db = db
        self.tamper_proof = AuditLogTamperProofService(db)

    def query_logs(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[AuditLog]:
        """查询审计日志"""
        query = self.db.query(AuditLog)

        if user_id:
            query = query.filter(AuditLog.user_id == user_id)
        if action:
            query = query.filter(AuditLog.action == action)
        if resource_type:
            query = query.filter(AuditLog.resource_type == resource_type)
        if start_time:
            query = query.filter(AuditLog.created_at >= start_time)
        if end_time:
            query = query.filter(AuditLog.created_at <= end_time)

        return query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()

    def get_user_activity(self, user_id: str, days: int = 30) -> dict:
        """获取用户活动统计"""
        start_time = datetime.utcnow() - timedelta(days=days)

        logs = self.db.query(AuditLog).filter(
            AuditLog.user_id == user_id,
            AuditLog.created_at >= start_time
        ).all()

        action_counts = {}
        resource_types = set()

        for log in logs:
            action_counts[log.action] = action_counts.get(log.action, 0) + 1
            if log.resource_type:
                resource_types.add(log.resource_type)

        return {
            "user_id": user_id,
            "period_days": days,
            "total_actions": len(logs),
            "action_breakdown": action_counts,
            "resource_types": list(resource_types),
            "first_activity": logs[-1].created_at if logs else None,
            "last_activity": logs[0].created_at if logs else None
        }

    def detect_anomalies(self, hours: int = 24) -> List[dict]:
        """检测异常活动"""
        from datetime import timedelta
        start_time = datetime.utcnow() - timedelta(hours=hours)

        anomalies = []

        # 检测频繁失败操作
        failed_logs = self.db.query(AuditLog).filter(
            AuditLog.action.like("%failed%"),
            AuditLog.created_at >= start_time
        ).all()

        for user_id in set(str(l.user_id) for l in failed_logs if l.user_id):
            user_failures = [l for l in failed_logs if str(l.user_id) == user_id]
            if len(user_failures) >= 5:
                anomalies.append({
                    "type": "frequent_failures",
                    "user_id": user_id,
                    "count": len(user_failures),
                    "severity": "high"
                })

        # 检测异常时间活动（深夜操作）
        midnight_logs = self.db.query(AuditLog).filter(
            AuditLog.created_at >= start_time,
            AuditLog.action.in_([
                "user_delete", "role_change", "permission_change",
                "config_change", "api_key_change"
            ])
        ).all()

        for log in midnight_logs:
            hour = log.created_at.hour
            if hour >= 0 and hour <= 5:
                anomalies.append({
                    "type": "unusual_time",
                    "user_id": str(log.user_id),
                    "action": log.action,
                    "time": log.created_at.isoformat(),
                    "severity": "medium"
                })

        return anomalies


from datetime import timedelta  # Add import at end to avoid circular