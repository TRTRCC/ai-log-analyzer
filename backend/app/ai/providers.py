"""
AI Provider Base Class and Multi-Provider Implementation
Supports: Claude, OpenAI, Azure OpenAI, Local models, and Custom providers
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from datetime import datetime
import json
import httpx

from app.config import settings
from app.utils.security import encrypt_value, decrypt_value
from app.utils.logging import get_logger
from app.utils.helpers import estimate_tokens

logger = get_logger(__name__)


class AnalysisResult:
    """Container for AI analysis results"""

    def __init__(
        self,
        success: bool,
        summary: Optional[str] = None,
        findings: Optional[List[Dict]] = None,
        recommendations: Optional[List[str]] = None,
        error: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model_used: Optional[str] = None,
        duration_ms: int = 0
    ):
        self.success = success
        self.summary = summary
        self.findings = findings or []
        self.recommendations = recommendations or []
        self.error = error
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model_used = model_used
        self.duration_ms = duration_ms
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "summary": self.summary,
            "findings": self.findings,
            "recommendations": self.recommendations,
            "error": self.error,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "model_used": self.model_used,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat()
        }


class AIProviderBase(ABC):
    """Abstract base class for AI providers"""

    provider_type: str = "base"
    default_model: str = ""

    def __init__(
        self,
        provider_id: str,
        name: str,
        api_endpoint: str,
        api_key: str,
        config: Optional[Dict] = None
    ):
        self.provider_id = provider_id
        self.name = name
        self.api_endpoint = api_endpoint
        self._api_key = api_key
        self.config = config or {}
        self._client = None

    @property
    def api_key(self) -> str:
        """Get decrypted API key"""
        if self._api_key.startswith('enc:'):
            return decrypt_value(self._api_key[4:])
        return self._api_key

    def set_api_key(self, key: str, encrypted: bool = False):
        """Set API key (optionally encrypted)"""
        if encrypted:
            self._api_key = 'enc:' + encrypt_value(key)
        else:
            self._api_key = key

    @abstractmethod
    async def initialize(self):
        """Initialize provider connection"""
        pass

    @abstractmethod
    async def analyze(
        self,
        prompt: str,
        context: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs
    ) -> AnalysisResult:
        """Perform analysis with AI model"""
        pass

    @abstractmethod
    async def get_available_models(self) -> List[str]:
        """Get list of available models"""
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test provider connection"""
        pass

    async def close(self):
        """Close provider connection"""
        if self._client:
            await self._client.aclose()
            self._client = None


class ClaudeProvider(AIProviderBase):
    """Anthropic Claude API provider"""

    provider_type = "claude"
    default_model = "claude-3-5-sonnet-20241022"

    async def initialize(self):
        """Initialize Claude client"""
        try:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(
                api_key=self.api_key,
                base_url=self.api_endpoint or "https://api.anthropic.com"
            )
            logger.info(f"Claude provider initialized: {self.name}")
        except ImportError:
            logger.warning("anthropic package not installed, using httpx")
            self._client = httpx.AsyncClient(
                base_url=self.api_endpoint or "https://api.anthropic.com",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                timeout=60.0
            )

    async def analyze(
        self,
        prompt: str,
        context: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs
    ) -> AnalysisResult:
        """Analyze logs with Claude"""
        start_time = datetime.utcnow()
        model = model or self.default_model

        # Build message
        messages = []
        if context:
            messages.append({"role": "user", "content": context})
        messages.append({"role": "user", "content": prompt})

        try:
            if hasattr(self._client, 'messages'):
                # Using anthropic SDK
                response = await self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=messages,
                    system=kwargs.get("system", "You are a log analysis expert. Analyze the provided logs and identify patterns, anomalies, security issues, and provide recommendations.")
                )

                content = response.content[0].text if response.content else ""
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
            else:
                # Using httpx
                payload = {
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": messages,
                    "system": kwargs.get("system", "You are a log analysis expert.")
                }
                resp = await self._client.post("/v1/messages", json=payload)
                resp.raise_for_status()
                data = resp.json()

                content = data.get("content", [{}])[0].get("text", "")
                input_tokens = data.get("usage", {}).get("input_tokens", 0)
                output_tokens = data.get("usage", {}).get("output_tokens", 0)

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            # Parse structured response
            result = self._parse_response(content)

            return AnalysisResult(
                success=True,
                summary=result.get("summary", content[:500]),
                findings=result.get("findings", []),
                recommendations=result.get("recommendations", []),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model_used=model,
                duration_ms=duration_ms
            )

        except Exception as e:
            logger.error(f"Claude analysis error: {e}")
            return AnalysisResult(success=False, error=str(e))

    def _parse_response(self, content: str) -> Dict:
        """Parse AI response into structured format"""
        try:
            # Try to parse as JSON if response is structured
            if content.strip().startswith('{'):
                return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Extract sections from text response
        result = {"summary": "", "findings": [], "recommendations": []}

        lines = content.split('\n')
        current_section = "summary"
        current_content = []

        for line in lines:
            if "## Summary" in line or "## summary" in line.lower():
                current_section = "summary"
            elif "## Findings" in line or "## findings" in line.lower():
                if current_content:
                    result[current_section] = '\n'.join(current_content).strip()
                current_section = "findings"
                current_content = []
            elif "## Recommendations" in line or "## recommendations" in line.lower():
                if current_content:
                    if current_section == "findings":
                        result["findings"] = [{"title": item.strip(), "description": ""}
                                              for item in current_content if item.strip()]
                    else:
                        result[current_section] = '\n'.join(current_content).strip()
                current_section = "recommendations"
                current_content = []
            else:
                current_content.append(line)

        # Final section
        if current_content:
            if current_section == "findings":
                result["findings"] = [{"title": item.strip(), "description": ""}
                                      for item in current_content if item.strip()]
            elif current_section == "recommendations":
                result["recommendations"] = [item.strip() for item in current_content if item.strip()]
            else:
                result[current_section] = '\n'.join(current_content).strip()

        return result

    async def get_available_models(self) -> List[str]:
        """Get Claude models"""
        return [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307"
        ]

    async def test_connection(self) -> bool:
        """Test Claude API connection"""
        try:
            result = await self.analyze("Say 'connection test successful'", max_tokens=50)
            return result.success
        except Exception:
            return False


class OpenAIProvider(AIProviderBase):
    """OpenAI GPT API provider"""

    provider_type = "openai"
    default_model = "gpt-4"

    async def initialize(self):
        """Initialize OpenAI client"""
        try:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.api_endpoint or "https://api.openai.com/v1"
            )
            logger.info(f"OpenAI provider initialized: {self.name}")
        except ImportError:
            logger.warning("openai package not installed, using httpx")
            self._client = httpx.AsyncClient(
                base_url=self.api_endpoint or "https://api.openai.com/v1",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                timeout=60.0
            )

    async def analyze(
        self,
        prompt: str,
        context: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs
    ) -> AnalysisResult:
        """Analyze logs with OpenAI"""
        start_time = datetime.utcnow()
        model = model or self.default_model

        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": prompt})

        try:
            if hasattr(self._client, 'chat'):
                # Using openai SDK
                response = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
                )

                content = response.choices[0].message.content if response.choices else ""
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens
            else:
                # Using httpx
                payload = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
                resp = await self._client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()

                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                input_tokens = data.get("usage", {}).get("prompt_tokens", 0)
                output_tokens = data.get("usage", {}).get("completion_tokens", 0)

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            result = self._parse_response(content)

            return AnalysisResult(
                success=True,
                summary=result.get("summary", content[:500]),
                findings=result.get("findings", []),
                recommendations=result.get("recommendations", []),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model_used=model,
                duration_ms=duration_ms
            )

        except Exception as e:
            logger.error(f"OpenAI analysis error: {e}")
            return AnalysisResult(success=False, error=str(e))

    def _parse_response(self, content: str) -> Dict:
        """Parse response into structured format"""
        try:
            if content.strip().startswith('{'):
                return json.loads(content)
        except json.JSONDecodeError:
            pass

        result = {"summary": content[:500], "findings": [], "recommendations": []}

        # Simple parsing logic similar to Claude
        if "findings:" in content.lower():
            parts = content.split("findings:")
            result["summary"] = parts[0].strip()
            if len(parts) > 1:
                findings_text = parts[1].split("recommendations:")[0]
                result["findings"] = [{"title": f.strip(), "description": ""}
                                      for f in findings_text.split('\n') if f.strip()]

        if "recommendations:" in content.lower():
            parts = content.split("recommendations:")
            if len(parts) > 1:
                result["recommendations"] = [r.strip()
                                            for r in parts[1].split('\n') if r.strip()]

        return result

    async def get_available_models(self) -> List[str]:
        """Get OpenAI models"""
        return ["gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-3.5-turbo"]

    async def test_connection(self) -> bool:
        """Test OpenAI connection"""
        try:
            result = await self.analyze("Say 'connection test successful'", max_tokens=50)
            return result.success
        except Exception:
            return False


class AzureOpenAIProvider(AIProviderBase):
    """Azure OpenAI API provider"""

    provider_type = "azure_openai"
    default_model = "gpt-4"

    async def initialize(self):
        """Initialize Azure OpenAI client"""
        deployment = self.config.get("deployment_name", self.default_model)
        api_version = self.config.get("api_version", "2024-02-15-preview")

        try:
            from openai import AsyncAzureOpenAI
            self._client = AsyncAzureOpenAI(
                api_key=self.api_key,
                api_version=api_version,
                azure_endpoint=self.api_endpoint,
                azure_deployment=deployment
            )
            logger.info(f"Azure OpenAI provider initialized: {self.name}")
        except ImportError:
            self._client = httpx.AsyncClient(
                base_url=f"{self.api_endpoint}/openai/deployments/{deployment}",
                headers={
                    "api-key": self.api_key,
                    "Content-Type": "application/json"
                },
                params={"api-version": api_version},
                timeout=60.0
            )

    async def analyze(
        self,
        prompt: str,
        context: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs
    ) -> AnalysisResult:
        """Analyze with Azure OpenAI"""
        start_time = datetime.utcnow()
        deployment = self.config.get("deployment_name", model or self.default_model)

        messages = []
        if context:
            messages.append({"role": "system", "content": context})
        messages.append({"role": "user", "content": prompt})

        try:
            if hasattr(self._client, 'chat'):
                response = await self._client.chat.completions.create(
                    model=deployment,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
                )

                content = response.choices[0].message.content if response.choices else ""
                input_tokens = response.usage.prompt_tokens
                output_tokens = response.usage.completion_tokens
            else:
                payload = {
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
                resp = await self._client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()

                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                input_tokens = data.get("usage", {}).get("prompt_tokens", 0)
                output_tokens = data.get("usage", {}).get("completion_tokens", 0)

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            return AnalysisResult(
                success=True,
                summary=content[:500],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model_used=deployment,
                duration_ms=duration_ms
            )

        except Exception as e:
            logger.error(f"Azure OpenAI analysis error: {e}")
            return AnalysisResult(success=False, error=str(e))

    async def get_available_models(self) -> List[str]:
        """Get available deployments"""
        return self.config.get("deployments", ["gpt-4", "gpt-35-turbo"])

    async def test_connection(self) -> bool:
        """Test Azure connection"""
        try:
            result = await self.analyze("Test", max_tokens=10)
            return result.success
        except Exception:
            return False


class LocalLLMProvider(AIProviderBase):
    """Local LLM provider (Ollama, vLLM, etc.)"""

    provider_type = "local"
    default_model = "llama2"

    async def initialize(self):
        """Initialize local LLM client"""
        self._client = httpx.AsyncClient(
            base_url=self.api_endpoint or "http://localhost:11434",
            timeout=120.0  # Local models may be slower
        )
        logger.info(f"Local LLM provider initialized: {self.name}")

    async def analyze(
        self,
        prompt: str,
        context: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs
    ) -> AnalysisResult:
        """Analyze with local LLM"""
        start_time = datetime.utcnow()
        model = model or self.default_model

        full_prompt = f"{context}\n\n{prompt}" if context else prompt

        try:
            # Ollama API format
            payload = {
                "model": model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature
                }
            }

            resp = await self._client.post("/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()

            content = data.get("response", "")
            # Ollama doesn't provide token counts directly
            input_tokens = estimate_tokens(full_prompt)
            output_tokens = estimate_tokens(content)

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            return AnalysisResult(
                success=True,
                summary=content[:500],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model_used=model,
                duration_ms=duration_ms
            )

        except Exception as e:
            logger.error(f"Local LLM analysis error: {e}")
            return AnalysisResult(success=False, error=str(e))

    async def get_available_models(self) -> List[str]:
        """Get local models"""
        try:
            resp = await self._client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m.get("name") for m in data.get("models", [])]
        except Exception:
            return ["llama2", "mistral", "codellama"]

    async def test_connection(self) -> bool:
        """Test local LLM connection"""
        try:
            resp = await self._client.get("/api/tags")
            return resp.status_code == 200
        except Exception:
            return False


class CustomProvider(AIProviderBase):
    """Custom AI provider with flexible API configuration"""

    provider_type = "custom"

    async def initialize(self):
        """Initialize custom provider"""
        headers = self.config.get("headers", {})
        headers["Content-Type"] = "application/json"

        if self.api_key:
            auth_header = self.config.get("auth_header", "Authorization")
            auth_format = self.config.get("auth_format", "Bearer {key}")
            headers[auth_header] = auth_format.replace("{key}", self.api_key)

        self._client = httpx.AsyncClient(
            base_url=self.api_endpoint,
            headers=headers,
            timeout=self.config.get("timeout", 60)
        )
        logger.info(f"Custom provider initialized: {self.name}")

    async def analyze(
        self,
        prompt: str,
        context: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs
    ) -> AnalysisResult:
        """Analyze with custom provider"""
        start_time = datetime.utcnow()

        # Use configurable request format
        request_format = self.config.get("request_format", "openai")

        if request_format == "openai":
            messages = []
            if context:
                messages.append({"role": "system", "content": context})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": model or self.config.get("default_model", ""),
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            endpoint = self.config.get("chat_endpoint", "/chat/completions")
        else:
            # Custom format
            payload = self.config.get("request_template", {}).copy()
            payload[self.config.get("prompt_field", "prompt")] = f"{context}\n{prompt}" if context else prompt
            if model:
                payload[self.config.get("model_field", "model")] = model
            endpoint = self.config.get("endpoint", "/generate")

        try:
            resp = await self._client.post(endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()

            # Parse response using configurable format
            response_format = self.config.get("response_format", "openai")
            if response_format == "openai":
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                input_tokens = data.get("usage", {}).get("prompt_tokens", estimate_tokens(prompt))
                output_tokens = data.get("usage", {}).get("completion_tokens", estimate_tokens(content))
            else:
                content_field = self.config.get("content_field", "response")
                content = data.get(content_field, "")
                input_tokens = estimate_tokens(prompt)
                output_tokens = estimate_tokens(content)

            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            return AnalysisResult(
                success=True,
                summary=content[:500],
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model_used=model,
                duration_ms=duration_ms
            )

        except Exception as e:
            logger.error(f"Custom provider analysis error: {e}")
            return AnalysisResult(success=False, error=str(e))

    async def get_available_models(self) -> List[str]:
        """Get available models"""
        return self.config.get("models", ["custom-model"])

    async def test_connection(self) -> bool:
        """Test custom provider connection"""
        try:
            endpoint = self.config.get("health_endpoint", "/health")
            resp = await self._client.get(endpoint)
            return resp.status_code == 200
        except Exception:
            return False


# Provider factory
PROVIDER_CLASSES = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "azure_openai": AzureOpenAIProvider,
    "local": LocalLLMProvider,
    "custom": CustomProvider
}


def create_provider(
    provider_type: str,
    provider_id: str,
    name: str,
    api_endpoint: str,
    api_key: str,
    config: Optional[Dict] = None
) -> AIProviderBase:
    """Create AI provider instance"""
    provider_class = PROVIDER_CLASSES.get(provider_type, CustomProvider)
    return provider_class(
        provider_id=provider_id,
        name=name,
        api_endpoint=api_endpoint,
        api_key=api_key,
        config=config
    )