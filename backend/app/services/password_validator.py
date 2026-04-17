"""
Password Validator - 等保三密码复杂度验证
"""

import re
from datetime import datetime, timedelta
from typing import List, Optional
import hashlib

from app.models.user import User


class PasswordValidator:
    """密码验证器 - 等保三密码复杂度要求"""

    # 等保三密码要求
    MIN_LENGTH = 8
    MAX_LENGTH = 32
    REQUIRE_UPPERCASE = True
    REQUIRE_LOWERCASE = True
    REQUIRE_DIGIT = True
    REQUIRE_SPECIAL = True
    SPECIAL_CHARS = "!@#$%^&*()_+-=[]{}|;:,.<>?/~`"
    PASSWORD_EXPIRE_DAYS = 90  # 密码有效期90天
    PASSWORD_HISTORY_SIZE = 5  # 保留最近5次密码

    def validate_password(self, password: str, user: Optional[User] = None) -> dict:
        """验证密码复杂度"""
        errors = []

        # 长度检查
        if len(password) < self.MIN_LENGTH:
            errors.append(f"密码长度至少{self.MIN_LENGTH}位")
        if len(password) > self.MAX_LENGTH:
            errors.append(f"密码长度最多{self.MAX_LENGTH}位")

        # 大写字母检查
        if self.REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
            errors.append("密码必须包含大写字母")

        # 小写字母检查
        if self.REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
            errors.append("密码必须包含小写字母")

        # 数字检查
        if self.REQUIRE_DIGIT and not re.search(r'\d', password):
            errors.append("密码必须包含数字")

        # 特殊字符检查
        if self.REQUIRE_SPECIAL:
            if not any(c in self.SPECIAL_CHARS for c in password):
                errors.append(f"密码必须包含特殊字符 ({self.SPECIAL_CHARS})")

        # 检查是否与用户名相似
        if user:
            if self._is_similar_to_username(password, user.username):
                errors.append("密码不能包含用户名")
            if user.email and self._is_similar_to_email(password, user.email):
                errors.append("密码不能包含邮箱信息")

        # 检查历史密码
        if user and user.password_history:
            if self._is_in_history(password, user.password_history):
                errors.append("密码不能与最近5次使用的密码相同")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "strength": self._calculate_strength(password)
        }

    def _calculate_strength(self, password: str) -> str:
        """计算密码强度"""
        score = 0

        # 长度评分
        if len(password) >= 8:
            score += 1
        if len(password) >= 12:
            score += 1
        if len(password) >= 16:
            score += 1

        # 字符类型评分
        if re.search(r'[A-Z]', password):
            score += 1
        if re.search(r'[a-z]', password):
            score += 1
        if re.search(r'\d', password):
            score += 1
        if any(c in self.SPECIAL_CHARS for c in password):
            score += 2

        # 评估强度
        if score <= 3:
            return "weak"
        elif score <= 5:
            return "medium"
        elif score <= 7:
            return "strong"
        else:
            return "very_strong"

    def _is_similar_to_username(self, password: str, username: str) -> bool:
        """检查密码是否包含用户名"""
        return username.lower() in password.lower()

    def _is_similar_to_email(self, password: str, email: str) -> bool:
        """检查密码是否包含邮箱信息"""
        email_parts = email.split('@')
        if len(email_parts) > 0:
            return email_parts[0].lower() in password.lower()
        return False

    def _is_in_history(self, password: str, history: List[str]) -> bool:
        """检查密码是否在历史记录中"""
        # 历史存储的是哈希值，需要哈希后比较
        password_hash = self._hash_password(password)
        return password_hash in history

    def _hash_password(self, password: str) -> str:
        """密码哈希（用于历史比对）"""
        return hashlib.sha256(password.encode()).hexdigest()

    def update_password_history(self, user: User, new_password_hash: str) -> List[str]:
        """更新密码历史"""
        history = user.password_history or []

        # 使用简化的哈希存储（实际密码存储用bcrypt）
        history.append(new_password_hash)

        # 保留最近5次
        if len(history) > self.PASSWORD_HISTORY_SIZE:
            history = history[-self.PASSWORD_HISTORY_SIZE:]

        return history

    def calculate_password_expiry(self) -> datetime:
        """计算密码过期时间"""
        return datetime.utcnow() + timedelta(days=self.PASSWORD_EXPIRE_DAYS)

    def generate_password_policy_message(self) -> str:
        """生成密码策略提示信息"""
        policy = [
            f"密码长度: {self.MIN_LENGTH}-{self.MAX_LENGTH}位",
            f"必须包含大写字母" if self.REQUIRE_UPPERCASE else None,
            f"必须包含小写字母" if self.REQUIRE_LOWERCASE else None,
            f"必须包含数字" if self.REQUIRE_DIGIT else None,
            f"必须包含特殊字符" if self.REQUIRE_SPECIAL else None,
            f"密码有效期: {self.PASSWORD_EXPIRE_DAYS}天",
            f"不能使用最近{self.PASSWORD_HISTORY_SIZE}次使用的密码"
        ]
        return "\n".join([p for p in policy if p])


class PasswordChangeService:
    """密码修改服务"""

    def __init__(self, password_validator: PasswordValidator):
        self.validator = password_validator

    def validate_change(
        self,
        user: User,
        old_password: str,
        new_password: str,
        verify_old: bool = True
    ) -> dict:
        """验证密码修改"""
        result = {
            "valid": True,
            "errors": []
        }

        # 验证旧密码（如果需要）
        if verify_old:
            # 这里需要调用auth服务验证旧密码
            # 暂时假设已验证
            pass

        # 验证新密码复杂度
        validation = self.validator.validate_password(new_password, user)
        if not validation["valid"]:
            result["valid"] = False
            result["errors"].extend(validation["errors"])

        # 检查新旧密码是否相同
        if old_password == new_password:
            result["valid"] = False
            result["errors"].append("新密码不能与旧密码相同")

        return result

    def apply_password_change(self, user: User, new_password_hash: str) -> dict:
        """应用密码修改"""
        now = datetime.utcnow()

        # 更新密码历史
        user.password_history = self.validator.update_password_history(
            user, new_password_hash
        )

        # 更新密码时间
        user.password_changed_at = now
        user.password_expires_at = self.validator.calculate_password_expiry()
        user.force_password_change = False

        return {
            "password_changed_at": now.isoformat(),
            "password_expires_at": user.password_expires_at.isoformat(),
            "history_size": len(user.password_history)
        }