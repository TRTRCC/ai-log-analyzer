"""
Configuration management for AI Log Analyzer
"""

import os
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

    # Security
    secret_key: str = Field(default="change-me-to-random-secret-key")
    jwt_secret_key: str = Field(default="change-me-to-random-jwt-secret")
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    jwt_refresh_expiration_days: int = 7
    password_hash_rounds: int = 12

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Convenience alias
settings = get_settings()