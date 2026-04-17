"""
Two Factor Authentication Service - 等保三双因子认证(TOTP)
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from datetime import datetime
from typing import List, Optional
from cryptography.fernet import Fernet

from app.models.user import User
from app.config import settings


class TOTPService:
    """TOTP双因子认证服务"""

    # TOTP配置
    DIGITS = 6  # 验证码位数
    PERIOD = 30  # 时间窗口（秒）
    WINDOW = 1  # 允许的时间窗口偏差

    def __init__(self):
        # 加密密钥（从配置获取）
        self.encryption_key = self._get_encryption_key()
        self.fernet = Fernet(self.encryption_key)

    def _get_encryption_key(self) -> bytes:
        """获取加密密钥"""
        # 从配置或环境变量获取
        key = getattr(settings, 'TOTP_ENCRYPTION_KEY', None)
        if not key:
            # 生成默认密钥（生产环境应从配置获取）
            key = base64.urlsafe_b64encode(os.urandom(32))
        return key if isinstance(key, bytes) else key.encode()

    def generate_secret(self) -> str:
        """生成TOTP密钥"""
        return base64.b32encode(os.urandom(20)).decode('utf-8')

    def encrypt_secret(self, secret: str) -> str:
        """加密存储密钥"""
        return self.fernet.encrypt(secret.encode()).decode()

    def decrypt_secret(self, encrypted_secret: str) -> str:
        """解密密钥"""
        return self.fernet.decrypt(encrypted_secret.encode()).decode()

    def generate_totp(self, secret: str) -> str:
        """生成TOTP验证码"""
        # 解码密钥
        key = base64.b32decode(secret, casefold=True)

        # 计算时间窗口
        timestamp = int(time.time() / self.PERIOD)

        # 打包时间戳
        msg = struct.pack('>Q', timestamp)

        # HMAC计算
        h = hmac.new(key, msg, hashlib.sha1).digest()

        # 动态截取
        offset = h[-1] & 0x0F
        code = struct.unpack('>I', h[offset:offset + 4])[0] & 0x7FFFFFFF

        # 取指定位数
        return str(code % (10 ** self.DIGITS)).zfill(self.DIGITS)

    def verify_totp(self, secret: str, code: str) -> bool:
        """验证TOTP码"""
        # 检查窗口内的多个时间戳（允许时间偏差）
        for window_offset in range(-self.WINDOW, self.WINDOW + 1):
            expected = self._generate_totp_at_offset(secret, window_offset)
            if expected == code:
                return True
        return False

    def _generate_totp_at_offset(self, secret: str, offset: int) -> str:
        """生成指定时间窗口的TOTP"""
        key = base64.b32decode(secret, casefold=True)
        timestamp = int(time.time() / self.PERIOD) + offset
        msg = struct.pack('>Q', timestamp)
        h = hmac.new(key, msg, hashlib.sha1).digest()
        offset_byte = h[-1] & 0x0F
        code = struct.unpack('>I', h[offset_byte:offset_byte + 4])[0] & 0x7FFFFFFF
        return str(code % (10 ** self.DIGITS)).zfill(self.DIGITS)

    def generate_backup_codes(self, count: int = 10) -> List[str]:
        """生成备用码"""
        codes = []
        for _ in range(count):
            # 生成8位随机码
            code = secrets.token_hex(4).upper()
            codes.append(code)
        return codes

    def hash_backup_code(self, code: str) -> str:
        """哈希备用码（用于存储）"""
        return hashlib.sha256(code.encode()).hexdigest()

    def verify_backup_code(self, user: User, code: str) -> bool:
        """验证备用码"""
        if not user.two_factor_backup_codes:
            return False

        code_hash = self.hash_backup_code(code)
        hashed_codes = user.two_factor_backup_codes

        if code_hash in hashed_codes:
            # 移除已使用的备用码
            hashed_codes.remove(code_hash)
            user.two_factor_backup_codes = hashed_codes
            return True

        return False

    def get_provisioning_uri(
        self,
        user: User,
        secret: str,
        issuer: str = "AI Log Analyzer"
    ) -> str:
        """生成 provisioning URI（用于QR码）"""
        return (
            f"otpauth://totp/{issuer}:{user.email}?secret={secret}&issuer={issuer}&digits={self.DIGITS}&period={self.PERIOD}"
        )


class TwoFactorAuthService:
    """双因子认证管理服务"""

    def __init__(self, db, totp_service: TOTPService):
        self.db = db
        self.totp = totp_service

    def setup_two_factor(self, user: User) -> dict:
        """启用双因子认证 - 第一步：生成密钥"""
        secret = self.totp.generate_secret()
        encrypted_secret = self.totp.encrypt_secret(secret)
        backup_codes = self.totp.generate_backup_codes()
        hashed_codes = [self.totp.hash_backup_code(c) for c in backup_codes]

        # 临时存储（需验证后正式启用）
        user.two_factor_secret_encrypted = encrypted_secret
        user.two_factor_backup_codes = hashed_codes
        self.db.commit()

        return {
            "secret": secret,  # 返回原始密钥供用户扫码
            "provisioning_uri": self.totp.get_provisioning_uri(user, secret),
            "backup_codes": backup_codes  # 返回原始备用码供用户保存
        }

    def verify_and_enable(self, user: User, verification_code: str) -> dict:
        """验证并正式启用双因子认证"""
        if not user.two_factor_secret_encrypted:
            return {"success": False, "error": "not_setup"}

        secret = self.totp.decrypt_secret(user.two_factor_secret_encrypted)

        if self.totp.verify_totp(secret, verification_code):
            user.two_factor_enabled = True
            user.two_factor_verified_at = datetime.utcnow()
            self.db.commit()
            return {"success": True}

        return {"success": False, "error": "invalid_code"}

    def verify_login(self, user: User, code: str) -> dict:
        """登录时验证双因子"""
        if not user.two_factor_enabled:
            return {"valid": True, "reason": "not_enabled"}

        # 支持TOTP码或备用码
        secret = self.totp.decrypt_secret(user.two_factor_secret_encrypted)

        # 先尝试TOTP验证
        if self.totp.verify_totp(secret, code):
            return {"valid": True, "method": "totp"}

        # 再尝试备用码验证
        if self.totp.verify_backup_code(user, code):
            self.db.commit()
            return {"valid": True, "method": "backup_code", "remaining_codes": len(user.two_factor_backup_codes)}

        return {"valid": False, "error": "invalid_code"}

    def disable_two_factor(self, user: User, verification_code: str) -> dict:
        """禁用双因子认证"""
        if not user.two_factor_enabled:
            return {"success": False, "error": "not_enabled"}

        # 验证当前TOTP码
        secret = self.totp.decrypt_secret(user.two_factor_secret_encrypted)
        if not self.totp.verify_totp(secret, verification_code):
            return {"success": False, "error": "invalid_code"}

        user.two_factor_enabled = False
        user.two_factor_secret_encrypted = None
        user.two_factor_backup_codes = None
        user.two_factor_verified_at = None
        self.db.commit()

        return {"success": True}

    def regenerate_backup_codes(self, user: User, verification_code: str) -> dict:
        """重新生成备用码"""
        if not user.two_factor_enabled:
            return {"success": False, "error": "not_enabled"}

        # 验证当前TOTP码
        secret = self.totp.decrypt_secret(user.two_factor_secret_encrypted)
        if not self.totp.verify_totp(secret, verification_code):
            return {"success": False, "error": "invalid_code"}

        # 生成新的备用码
        backup_codes = self.totp.generate_backup_codes()
        hashed_codes = [self.totp.hash_backup_code(c) for c in backup_codes]
        user.two_factor_backup_codes = hashed_codes
        self.db.commit()

        return {"success": True, "backup_codes": backup_codes}

    def get_status(self, user: User) -> dict:
        """获取双因子认证状态"""
        return {
            "enabled": user.two_factor_enabled,
            "verified_at": user.two_factor_verified_at.isoformat() if user.two_factor_verified_at else None,
            "backup_codes_remaining": len(user.two_factor_backup_codes) if user.two_factor_backup_codes else 0
        }