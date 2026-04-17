"""
AI Analysis Engine - Unified interface for multiple AI providers
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from uuid import UUID
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.ai.providers import (
    AIProviderBase,
    AnalysisResult,
    create_provider,
    PROVIDER_CLASSES
)
from app.models import AIProvider, AIModel, AnalysisTask, TaskStatus, AIUsageLog
from app.utils.logging import get_logger
from app.utils.helpers import estimate_tokens, generate_uuid

logger = get_logger(__name__)


class AIEngine:
    """Unified AI analysis engine"""

    _providers: Dict[str, AIProviderBase] = {}
    _initialized: bool = False

    async def initialize(self, db_session: AsyncSession):
        """Initialize all active AI providers"""
        if self._initialized:
            return

        # Load providers from database
        result = await db_session.execute(
            select(AIProvider).where(AIProvider.is_active == True)
        )
        providers = result.scalars().all()

        for provider in providers:
            try:
                instance = create_provider(
                    provider_type=provider.provider_type,
                    provider_id=str(provider.id),
                    name=provider.name,
                    api_endpoint=provider.api_endpoint,
                    api_key=provider.api_key_encrypted or "",
                    config=provider.config
                )
                await instance.initialize()
                self._providers[str(provider.id)] = instance
                logger.info(f"Provider {provider.name} initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize provider {provider.name}: {e}")

        self._initialized = True
        logger.info(f"AI Engine initialized with {len(self._providers)} providers")

    async def get_provider(self, provider_id: str) -> Optional[AIProviderBase]:
        """Get provider instance by ID"""
        return self._providers.get(provider_id)

    async def get_default_provider(self, db_session: AsyncSession) -> Optional[AIProviderBase]:
        """Get default provider"""
        result = await db_session.execute(
            select(AIProvider).where(
                AIProvider.is_active == True,
                AIProvider.is_default == True
            )
        )
        provider = result.scalar_one_or_none()

        if provider:
            return self._providers.get(str(provider.id))

        # Return first available provider if no default
        if self._providers:
            return list(self._providers.values())[0]

        return None

    async def analyze_logs(
        self,
        db_session: AsyncSession,
        task_id: UUID,
        logs_sample: str,
        analysis_type: str = "general",
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None
    ) -> AnalysisResult:
        """
        Perform log analysis with AI

        Args:
            db_session: Database session
            task_id: Analysis task ID
            logs_sample: Sample of logs to analyze
            analysis_type: Type of analysis (general, security, performance, network)
            provider_id: Specific provider to use (optional)
            model_id: Specific model to use (optional)

        Returns:
            AnalysisResult with findings and recommendations
        """

        # Get provider
        if provider_id:
            provider = await self.get_provider(provider_id)
        else:
            provider = await self.get_default_provider(db_session)

        if not provider:
            return AnalysisResult(success=False, error="No AI provider available")

        # Get model info
        model_name = None
        if model_id:
            result = await db_session.execute(
                select(AIModel).where(AIModel.id == UUID(model_id))
            )
            model = result.scalar_one_or_none()
            if model:
                model_name = model.model_name
                max_tokens = model.max_tokens or 4096
            else:
                max_tokens = 4096
        else:
            max_tokens = 4096
            model_name = provider.default_model

        # Build analysis prompt based on type
        prompt = self._build_analysis_prompt(logs_sample, analysis_type)

        # Update task status
        await db_session.execute(
            update(AnalysisTask)
            .where(AnalysisTask.id == task_id)
            .values(status=TaskStatus.RUNNING, started_at=datetime.utcnow())
        )
        await db_session.commit()

        # Perform analysis
        try:
            result = await provider.analyze(
                prompt=prompt,
                model=model_name,
                max_tokens=max_tokens,
                temperature=0.7,
                system=self._get_system_prompt(analysis_type)
            )

            # Update task with results
            await db_session.execute(
                update(AnalysisTask)
                .where(AnalysisTask.id == task_id)
                .values(
                    status=TaskStatus.COMPLETED if result.success else TaskStatus.FAILED,
                    result=result.to_dict(),
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    completed_at=datetime.utcnow(),
                    error_message=result.error if not result.success else None
                )
            )

            # Log AI usage
            usage_log = AIUsageLog(
                user_id=None,  # Will be updated later
                provider_id=UUID(provider_id) if provider_id else None,
                model_id=UUID(model_id) if model_id else None,
                task_id=task_id,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost=json.dumps({
                    "input_cost": self._calculate_cost(result.input_tokens, "input", model),
                    "output_cost": self._calculate_cost(result.output_tokens, "output", model),
                }),
                request_duration_ms=result.duration_ms
            )
            db_session.add(usage_log)

            await db_session.commit()

            return result

        except Exception as e:
            logger.error(f"Analysis failed for task {task_id}: {e}")

            await db_session.execute(
                update(AnalysisTask)
                .where(AnalysisTask.id == task_id)
                .values(status=TaskStatus.FAILED, error_message=str(e))
            )
            await db_session.commit()

            return AnalysisResult(success=False, error=str(e))

    def _build_analysis_prompt(self, logs_sample: str, analysis_type: str) -> str:
        """Build analysis prompt based on log content and type"""

        prompts = {
            "general": """
Please analyze the following log entries and provide:
1. A summary of key events and patterns
2. Any anomalies or unusual behavior detected
3. Security concerns or potential threats
4. Performance issues identified
5. Recommendations for investigation or action

Format your response with clear sections:
## Summary
[Brief overview]

## Findings
[List each finding with details]

## Recommendations
[Specific actionable recommendations]

Log entries:
{logs}
""",
            "security": """
Perform a security-focused analysis on these logs:
1. Identify potential security threats (unauthorized access, attacks, suspicious activity)
2. Detect anomalies that may indicate compromise
3. List all authentication-related events
4. Identify network connections that may be malicious
5. Provide security recommendations

Log entries:
{logs}
""",
            "performance": """
Analyze these logs for performance issues:
1. Identify any performance degradation indicators
2. Find resource usage anomalies (CPU, memory, disk)
3. Detect slow operations or timeouts
4. List error patterns that affect performance
5. Provide optimization recommendations

Log entries:
{logs}
""",
            "network": """
Analyze these network-related logs:
1. Identify connectivity issues or failures
2. Detect unusual network traffic patterns
3. Find interface errors or flapping
4. Identify potential network attacks
5. Provide network troubleshooting recommendations

Log entries:
{logs}
"""
        }

        template = prompts.get(analysis_type, prompts["general"])
        return template.format(logs=logs_sample)

    def _get_system_prompt(self, analysis_type: str) -> str:
        """Get system prompt for AI"""

        system_prompts = {
            "general": "You are an expert log analyst. Analyze the provided logs comprehensively and provide structured insights.",
            "security": "You are a cybersecurity expert. Focus on identifying security threats, vulnerabilities, and suspicious activities in the logs.",
            "performance": "You are a system performance expert. Analyze logs to identify performance bottlenecks and optimization opportunities.",
            "network": "You are a network engineer. Analyze network logs to identify connectivity issues, traffic anomalies, and configuration problems."
        }

        return system_prompts.get(analysis_type, system_prompts["general"])

    def _calculate_cost(self, tokens: int, token_type: str, model: Optional[AIModel]) -> float:
        """Calculate cost for token usage"""
        if not model:
            return 0.0

        if token_type == "input":
            rate = model.cost_per_1k_input_tokens or 0
        else:
            rate = model.cost_per_1k_output_tokens or 0

        return (tokens / 1000) * float(rate)

    async def add_provider(
        self,
        db_session: AsyncSession,
        provider_type: str,
        name: str,
        api_endpoint: str,
        api_key: str,
        config: Optional[Dict] = None,
        is_default: bool = False
    ) -> AIProvider:
        """Add new AI provider"""

        provider = AIProvider(
            name=name,
            display_name=name,
            provider_type=provider_type,
            api_endpoint=api_endpoint,
            api_key_encrypted=api_key,
            is_active=True,
            is_default=is_default,
            config=config
        )
        db_session.add(provider)
        await db_session.commit()
        await db_session.refresh(provider)

        # Initialize provider instance
        instance = create_provider(
            provider_type=provider_type,
            provider_id=str(provider.id),
            name=name,
            api_endpoint=api_endpoint,
            api_key=api_key,
            config=config
        )
        await instance.initialize()
        self._providers[str(provider.id)] = instance

        logger.info(f"New provider {name} added and initialized")
        return provider

    async def remove_provider(self, db_session: AsyncSession, provider_id: UUID):
        """Remove AI provider"""
        # Close and remove instance
        if str(provider_id) in self._providers:
            await self._providers[str(provider_id)].close()
            del self._providers[str(provider_id)]

        # Update database
        await db_session.execute(
            update(AIProvider)
            .where(AIProvider.id == provider_id)
            .values(is_active=False)
        )
        await db_session.commit()

    async def test_provider(self, provider_id: str) -> bool:
        """Test provider connection"""
        provider = self._providers.get(provider_id)
        if provider:
            return await provider.test_connection()
        return False

    async def close_all(self):
        """Close all provider connections"""
        for provider in self._providers.values():
            await provider.close()
        self._providers.clear()
        self._initialized = False


# Global engine instance
ai_engine = AIEngine()


async def get_ai_engine() -> AIEngine:
    """Get AI engine instance"""
    return ai_engine