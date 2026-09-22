"""
Application configuration using Pydantic BaseSettings.
All configuration is loaded from environment variables or .env file with VFD_ prefix.
"""

from pathlib import Path
from typing import Optional
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Gateway Security
    api_key: str = Field("vfd-dev-secret-key-12345", description="API Key for gateway authentication")
    
    # Blockchain / Fabric Bridge Configuration
    enforce_model_registry: bool = Field(
        True,
        description="Verify loaded models and rules against on-chain ModelRegistry. Defaults to True.",
    )
    fabric_bridge_url: str = Field(
        "http://127.0.0.1:8081",
        description="Base URL for Node/TypeScript fabric-bridge service bound to 127.0.0.1",
    )
    fabric_bridge_api_key: Optional[str] = Field(
        None,
        description="API Key for fabric-bridge service. NO DEFAULT. Required from environment when bridge is used.",
    )
    vfd_hmac_secret: str = Field(
        "vfd-offline-hmac-salt-secure-seed",
        description="Off-chain secret key for computing pseudonymous subjectRef and consentHash",
    )
    model_registry_cache_ttl_s: int = Field(
        300,
        description="Time-to-live in seconds for caching endorsed on-chain model/rules hashes",
    )

    # Storage & Database
    database_url: str = Field(
        "postgresql://vfd:changeme@127.0.0.1:5432/voice_fraud",
        description="PostgreSQL DSN for audit chain and transactional outbox",
    )
    audio_storage_path: Path = Field(Path("/data/audio"), description="Off-chain encrypted audio store")
    
    # Rules & Config
    rules_yaml_path: Path = Field(
        Path(__file__).resolve().parent.parent / "risk_engine" / "rules.yaml",
        description="Path to rules.yaml",
    )
    
    # Upload limits
    max_upload_bytes: int = Field(50 * 1024 * 1024, description="Maximum upload size in bytes (50 MB)")
    allowed_content_types: list[str] = Field(
        ["audio/wav", "audio/x-wav", "audio/wave", "audio/mpeg", "audio/ogg", "audio/flac", "application/octet-stream"],
        description="Permitted MIME types for audio uploads",
    )
    
    # Server
    host: str = Field("127.0.0.1")
    port: int = Field(8000)
    log_level: str = Field("INFO")
    stub_delay_ms: float = Field(0.0)

    model_config = {
        "env_prefix": "VFD_",
        "env_file": ".env",
        "extra": "ignore",
    }

    def validate_fabric_credentials(self) -> None:
        """Fail fast at startup if enforce_model_registry is enabled without API key."""
        if self.enforce_model_registry and not self.fabric_bridge_api_key:
            raise ValueError(
                "Security Error: enforce_model_registry is enabled, but VFD_FABRIC_BRIDGE_API_KEY is not set. "
                "Set VFD_FABRIC_BRIDGE_API_KEY in your environment or .env."
            )


settings = Settings()
