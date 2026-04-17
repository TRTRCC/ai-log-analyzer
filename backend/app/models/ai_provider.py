"""
AI Provider and Model configurations
"""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Text, UUID, Integer, Numeric, JSON
)
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class ProviderType(str, enum.Enum):
    """AI provider type enumeration"""
    CLAUDE = "claude"
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    LOCAL = "local"
    CUSTOM = "custom"


class AIProvider(Base):
    """AI service provider configuration"""
    __tablename__ = "ai_providers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), unique=True, nullable=False)
    display_name = Column(String(100), nullable=True)
    provider_type = Column(String(20), nullable=False)
    api_endpoint = Column(String(255), nullable=True)
    api_key_encrypted = Column(Text, nullable=True)  # Encrypted API key
    models = Column(JSON, nullable=True)  # List of available models
    is_active = Column(Boolean, default=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    config = Column(JSON, nullable=True)  # Additional configuration
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    ai_models = relationship("AIModel", back_populates="provider")
    tasks = relationship("AnalysisTask", back_populates="provider")

    def __repr__(self):
        return f"<AIProvider {self.name}>"

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """Get a configuration value"""
        if self.config is None:
            return default
        return self.config.get(key, default)


class AIModel(Base):
    """AI model configuration"""
    __tablename__ = "ai_models"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("ai_providers.id"), nullable=False)
    model_name = Column(String(100), nullable=False)
    display_name = Column(String(100), nullable=True)
    max_tokens = Column(Integer, nullable=True)
    cost_per_1k_input_tokens = Column(Numeric(10, 6), nullable=True)
    cost_per_1k_output_tokens = Column(Numeric(10, 6), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    config = Column(JSON, nullable=True)  # Model-specific configuration
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    provider = relationship("AIProvider", back_populates="ai_models")
    tasks = relationship("AnalysisTask", back_populates="model")

    def __repr__(self):
        return f"<AIModel {self.model_name}>"

    @property
    def full_name(self) -> str:
        """Get full model name with provider"""
        return f"{self.provider.name}/{self.model_name}"