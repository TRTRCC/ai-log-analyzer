"""
Configuration management for AI Log Analyzer - 等保三合规版本
"""

import os
import base64
from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment"""

    # Application
    app_name: str = "AI Log Analyzer"
    app_version: str = "1.0.0"
    debug: bool = False
    project_dir: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Database
    database_url: str = Field(default="postgresql://ailoguser:password@localhost:5432/ailoganalyzer")
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # ClickHouse
    clickhouse_url: str = Field(default="http://localhost:8123")
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "ailoganalyzer_logs"

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0")
    redis_max_connections: int = 50

    # === 等保三安全配置 ===
    # Security
    secret_key: str = Field(default="change-me-to-random-secret-key")
    jwt_secret_key: str = Field(default="change-me-to-random-jwt-secret")
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    jwt_refresh_expiration_days: int = 7
    password_hash_rounds: int = 12

    # 等保三：登录锁定参数
    login_max_failures: int = 5
    login_lockout_duration_minutes: int = 30
    login_failure_window_minutes: int = 15

    # 等保三：密码策略
    password_min_length: int = 8
    password_max_length: int = 32
    password_require_uppercase: bool = True
    password_require_lowercase: bool = True
    password_require_digit: bool = True
    password_require_special: bool = True
    password_expire_days: int = 90
    password_history_size: int = 5

    # 等保三：会话管理
    session_max_concurrent: int = 5
    session_timeout_minutes: int = 30

    # 等保三：2FA/TOTP加密密钥
    totp_encryption_key: Optional[str] = None

    # 等保三：备份加密密钥
    backup_encryption_key: Optional[str] = None

    # Admin
    admin_email: str = "admin@example.com"
    admin_password: str = "admin123"

    # Data directories
    data_dir: str = "/data"
    raw_log_dir: str = "/data/raw"
    parsed_log_dir: str = "/data/parsed"
    report_dir: str = "/data/reports"
    audit_dir: str = "/data/audit"

    # CORS
    cors_origins: List[str] = ["http://localhost", "http://localhost:80"]

    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_period_seconds: int = 60

    # 等保三：入侵检测参数
    intrusion_detection_enabled: bool = True
    ip_block_duration_minutes: int = 60

    # AI Providers (optional defaults)
    claude_api_key: Optional[str] = None
    claude_api_url: str = "https://api.anthropic.com"
    openai_api_key: Optional[str] = None
    openai_api_url: str = "https://api.openai.com/v1"
    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_deployment: Optional[str] = None

    # Email
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from_email: Optional[str] = None
    smtp_use_tls: bool = True

    # Logging
    log_level: str = "INFO"
    log_file: str = "/data/audit/app.log"

    # Task scheduling
    daily_report_hour: int = 8
    auto_analysis_interval_hours: int = 6

    # 等保三：备份参数
    backup_retention_days: int = 30
    backup_interval_hours: int = 24
    backup_max_count: int = 30

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 生成默认加密密钥（如果未配置）
        if not self.totp_encryption_key:
            self.totp_encryption_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
        if not self.backup_encryption_key:
            self.backup_encryption_key = base64.urlsafe_b64encode(os.urandom(32)).decode()


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Convenience alias
settings = get_settings()