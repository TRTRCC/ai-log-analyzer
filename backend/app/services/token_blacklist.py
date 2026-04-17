"""
Token Blacklist Service - 等保三Token黑名单与注销管理
"""

import hashlib
from datetime import datetime, timedelta
from typing import Optional
import redis
import json

from app.config import settings


class TokenBlacklistService:
    """Token黑名单服务 - Redis实现"""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.blacklist_prefix = "token_blacklist:"
        self.user_tokens_prefix = "user_tokens:"

    def blacklist_token(self, token: str, expires_at: datetime, reason: str = "logout") -> bool:
        """将Token加入黑名单"""
        token_hash = self._hash_token(token)
        key = f"{self.blacklist_prefix}{token_hash}"

        # 计算黑名单保留时间（Token过期时间）
        ttl = max(1, int((expires_at - datetime.utcnow()).total_seconds()))

        # 存储黑名单信息
        data = {
            "reason": reason,
            "blacklisted_at": datetime.utcnow().isoformat(),
            "expires_at": expires_at.isoformat()
        }

        self.redis.setex(key, ttl, json.dumps(data))
        return True

    def is_blacklisted(self, token: str) -> bool:
        """检查Token是否在黑名单中"""
        token_hash = self._hash_token(token)
        key = f"{self.blacklist_prefix}{token_hash}"
        return self.redis.exists(key)

    def get_blacklist_info(self, token: str) -> Optional[dict]:
        """获取黑名单信息"""
        token_hash = self._hash_token(token)
        key = f"{self.blacklist_prefix}{token_hash}"
        data = self.redis.get(key)
        if data:
            return json.loads(data)
        return None

    def blacklist_all_user_tokens(self, user_id: str, reason: str = "force_logout"):
        """黑名单用户所有Token"""
        key = f"{self.user_tokens_prefix}{user_id}"
        tokens = self.redis.smembers(key)

        for token_hash in tokens:
            blacklist_key = f"{self.blacklist_prefix}{token_hash}"
            data = {
                "reason": reason,
                "blacklisted_at": datetime.utcnow().isoformat(),
                "user_id": user_id
            }
            # 设置足够长的黑名单时间
            self.redis.setex(blacklist_key, 86400 * 7, json.dumps(data))

        # 清除用户Token集合
        self.redis.delete(key)

        return len(tokens)

    def track_user_token(self, user_id: str, token: str, expires_at: datetime):
        """追踪用户Token"""
        token_hash = self._hash_token(token)
        key = f"{self.user_tokens_prefix}{user_id}"

        # 添加到用户Token集合
        self.redis.sadd(key, token_hash)

        # 设置集合过期时间（与最长Token同步）
        self.redis.expireat(key, int(expires_at.timestamp()))

    def remove_user_token(self, user_id: str, token: str):
        """从用户Token集合移除"""
        token_hash = self._hash_token(token)
        key = f"{self.user_tokens_prefix}{user_id}"
        self.redis.srem(key, token_hash)

    def get_user_active_tokens(self, user_id: str) -> int:
        """获取用户活跃Token数量"""
        key = f"{self.user_tokens_prefix}{user_id}"
        return self.redis.scard(key)

    def _hash_token(self, token: str) -> str:
        """Token哈希"""
        return hashlib.sha256(token.encode()).hexdigest()


class RefreshTokenService:
    """Refresh Token管理服务"""

    # Refresh Token有效期（7天）
    REFRESH_TOKEN_EXPIRE_DAYS = 7

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.refresh_prefix = "refresh_token:"
        self.user_refresh_prefix = "user_refresh:"

    def store_refresh_token(self, user_id: str, refresh_token: str, expires_at: datetime):
        """存储Refresh Token"""
        token_hash = self._hash_token(refresh_token)
        key = f"{self.refresh_prefix}{token_hash}"

        # 存储用户ID
        ttl = int((expires_at - datetime.utcnow()).total_seconds())
        self.redis.setex(key, ttl, user_id)

        # 追踪用户Refresh Token
        user_key = f"{self.user_refresh_prefix}{user_id}"
        self.redis.sadd(user_key, token_hash)
        self.redis.expireat(user_key, int(expires_at.timestamp()))

    def validate_refresh_token(self, refresh_token: str) -> Optional[str]:
        """验证Refresh Token，返回用户ID"""
        token_hash = self._hash_token(refresh_token)
        key = f"{self.refresh_prefix}{token_hash}"
        user_id = self.redis.get(key)

        if user_id:
            return user_id.decode() if isinstance(user_id, bytes) else user_id
        return None

    def revoke_refresh_token(self, refresh_token: str):
        """撤销Refresh Token"""
        token_hash = self._hash_token(refresh_token)
        key = f"{self.refresh_prefix}{token_hash}"

        # 获取用户ID
        user_id = self.redis.get(key)
        if user_id:
            user_key = f"{self.user_refresh_prefix}{user_id}"
            self.redis.srem(user_key, token_hash)

        # 删除Token
        self.redis.delete(key)

    def revoke_all_user_refresh_tokens(self, user_id: str):
        """撤销用户所有Refresh Token"""
        user_key = f"{self.user_refresh_prefix}{user_id}"
        token_hashes = self.redis.smembers(user_key)

        for token_hash in token_hashes:
            key = f"{self.refresh_prefix}{token_hash}"
            self.redis.delete(key)

        self.redis.delete(user_key)
        return len(token_hashes)

    def rotate_refresh_token(self, old_token: str, new_token: str, user_id: str, expires_at: datetime):
        """轮换Refresh Token（安全最佳实践）"""
        # 撤销旧Token
        self.revoke_refresh_token(old_token)

        # 存储新Token
        self.store_refresh_token(user_id, new_token, expires_at)

    def _hash_token(self, token: str) -> str:
        """Token哈希"""
        return hashlib.sha256(token.encode()).hexdigest()


class TokenRevocationManager:
    """Token注销管理器"""

    def __init__(
        self,
        blacklist_service: TokenBlacklistService,
        refresh_service: RefreshTokenService
    ):
        self.blacklist = blacklist_service
        self.refresh = refresh_service

    def logout_single_session(self, access_token: str, refresh_token: str, access_expires: datetime):
        """注销单个会话"""
        # 黑名单Access Token
        self.blacklist.blacklist_token(access_token, access_expires, reason="logout")

        # 撤销Refresh Token
        if refresh_token:
            self.refresh.revoke_refresh_token(refresh_token)

    def logout_all_sessions(self, user_id: str, current_access_token: str, access_expires: datetime):
        """注销用户所有会话（除当前）"""
        # 黑名单所有Access Token
        count = self.blacklist.blacklist_all_user_tokens(user_id, reason="logout_all")

        # 撤销所有Refresh Token
        refresh_count = self.refresh.revoke_all_user_refresh_tokens(user_id)

        return {
            "access_tokens_revoked": count,
            "refresh_tokens_revoked": refresh_count
        }

    def force_logout_user(self, user_id: str, reason: str = "security_incident"):
        """强制注销用户（安全事件）"""
        # 黑名单所有Token
        count = self.blacklist.blacklist_all_user_tokens(user_id, reason=reason)

        # 撤销所有Refresh Token
        refresh_count = self.refresh.revoke_all_user_refresh_tokens(user_id)

        return {
            "reason": reason,
            "tokens_revoked": count + refresh_count
        }