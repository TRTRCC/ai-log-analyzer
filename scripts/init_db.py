"""
Database initialization script
Creates initial admin user and default configurations
"""

import asyncio
import os
from uuid import UUID
from datetime import datetime

from app.config import settings
from app.database import async_session_factory, init_database
from app.models import (
    User, UserRole, Department, AIProvider, AIModel,
    ScheduledTask, FrontendModule, StorageConfig, EmailConfig
)
from app.utils.security import hash_password, encrypt_value


async def init_db():
    """Initialize database with default data"""

    await init_database()

    async with async_session_factory() as db:
        # Create default departments
        departments = [
            ("Network Team", "Network device management team"),
            ("Server Team", "Server infrastructure team"),
            ("K8S Team", "Kubernetes cluster management team"),
            ("Audit Team", "Security and compliance audit team"),
            ("IT Admin", "IT administration team"),
        ]

        for name, desc in departments:
            dept = Department(name=name, description=desc)
            db.add(dept)

        await db.commit()

        # Create admin user
        admin_dept = await db.execute(
            "SELECT id FROM departments WHERE name = 'IT Admin'"
        )
        admin_dept_id = admin_dept.scalar()

        admin_user = User(
            username="admin",
            email=settings.admin_email,
            password_hash=hash_password(settings.admin_password),
            role=UserRole.SUPER_ADMIN,
            department_id=admin_dept_id,
            is_active=True,
            is_superuser=True,
        )
        db.add(admin_user)

        # Create default AI providers (without API keys - user needs to configure)
        default_providers = [
            {
                "name": "claude",
                "display_name": "Claude (Anthropic)",
                "provider_type": "claude",
                "api_endpoint": "https://api.anthropic.com",
                "is_default": True,
                "models": [
                    {"name": "claude-3-5-sonnet-20241022", "display": "Claude 3.5 Sonnet", "max_tokens": 8192, "cost_in": 0.003, "cost_out": 0.015},
                    {"name": "claude-3-5-haiku-20241022", "display": "Claude 3.5 Haiku", "max_tokens": 8192, "cost_in": 0.001, "cost_out": 0.005},
                ]
            },
            {
                "name": "openai",
                "display_name": "OpenAI",
                "provider_type": "openai",
                "api_endpoint": "https://api.openai.com/v1",
                "is_default": False,
                "models": [
                    {"name": "gpt-4", "display": "GPT-4", "max_tokens": 8192, "cost_in": 0.03, "cost_out": 0.06},
                    {"name": "gpt-4-turbo", "display": "GPT-4 Turbo", "max_tokens": 4096, "cost_in": 0.01, "cost_out": 0.03},
                ]
            },
            {
                "name": "azure_openai",
                "display_name": "Azure OpenAI",
                "provider_type": "azure_openai",
                "is_default": False,
                "models": [
                    {"name": "gpt-4", "display": "GPT-4 (Azure)", "max_tokens": 8192},
                ]
            },
            {
                "name": "local_ollama",
                "display_name": "Local Model (Ollama)",
                "provider_type": "local",
                "api_endpoint": "http://localhost:11434",
                "is_default": False,
                "models": [
                    {"name": "llama2", "display": "Llama 2", "max_tokens": 4096},
                    {"name": "mistral", "display": "Mistral", "max_tokens": 4096},
                ]
            },
        ]

        for prov_data in default_providers:
            provider = AIProvider(
                name=prov_data["name"],
                display_name=prov_data["display_name"],
                provider_type=prov_data["provider_type"],
                api_endpoint=prov_data.get("api_endpoint"),
                is_active=True,
                is_default=prov_data["is_default"],
            )
            db.add(provider)
            await db.commit()
            await db.refresh(provider)

            # Add models
            for model_data in prov_data.get("models", []):
                model = AIModel(
                    provider_id=provider.id,
                    model_name=model_data["name"],
                    display_name=model_data["display"],
                    max_tokens=model_data.get("max_tokens", 4096),
                    cost_per_1k_input_tokens=model_data.get("cost_in"),
                    cost_per_1k_output_tokens=model_data.get("cost_out"),
                    is_active=True,
                    is_default=prov_data["is_default"] and prov_data["models"][0]["name"] == model_data["name"],
                )
                db.add(model)

        await db.commit()

        # Create scheduled tasks
        scheduled_tasks = [
            ("Daily Report Generation", "daily_report", "0 8 * * *", True),
            ("Auto Analysis (Every 6 hours)", "auto_analysis", "0 */6 * * *", True),
            ("Log Cleanup (Weekly)", "log_cleanup", "0 0 * * 0", False),
        ]

        for name, task_type, cron, active in scheduled_tasks:
            task = ScheduledTask(
                name=name,
                task_type=task_type,
                cron_expression=cron,
                is_active=active,
            )
            db.add(task)

        await db.commit()

        # Create frontend modules
        frontend_modules = [
            ("dashboard", "Dashboard", True, ["*"], 1),
            ("logs", "Log Query", True, ["*"], 2),
            ("analysis", "AI Analysis", True, ["*"], 3),
            ("reports", "Reports", True, ["*"], 4),
            ("charts", "Charts", True, ["*"], 5),
            ("profile", "Profile", True, ["*"], 6),
            ("admin", "Admin Panel", True, ["super_admin", "audit_admin", "dept_admin"], 7),
        ]

        for key, name, enabled, roles, order in frontend_modules:
            module = FrontendModule(
                module_key=key,
                module_name=name,
                is_enabled=enabled,
                roles_allowed=roles,
                sort_order=order,
            )
            db.add(module)

        await db.commit()

        # Create storage configs
        storage_configs = [
            ("raw_logs", settings.raw_log_dir, "Raw ELK log files", None, None),
            ("parsed_logs", settings.parsed_log_dir, "Parsed and structured logs", None, None),
            ("reports", settings.report_dir, "Analysis reports", None, None),
            ("audit", settings.audit_dir, "Audit logs", None, None),
        ]

        for key, path, desc, max_size, retention in storage_configs:
            config = StorageConfig(
                config_key=key,
                directory_path=path,
                description=desc,
                max_size_mb=max_size,
                retention_days=retention,
            )
            db.add(config)

        await db.commit()

        print("Database initialized successfully!")
        print(f"Admin user created: {settings.admin_email}")
        print("Please configure AI provider API keys in the admin panel.")


if __name__ == "__main__":
    asyncio.run(init_db())