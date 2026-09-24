"""
Application configuration using Pydantic BaseSettings.
All configuration is loaded from environment variables or .env file with VFD_ prefix.
"""

from pathlib import Path
from typing import Literal, Optional
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

    # Telephony ingress (provider-neutral; all optional, placeholders only)
    telephony_provider: str = Field(
        "",
        description="Telephony provider name (e.g. 'twilio'). Empty means no provider configured.",
    )
    telephony_api_key: Optional[str] = Field(
        None, description="Provider API key SID/identifier. Never committed; env only."
    )
    telephony_api_secret: Optional[str] = Field(
        None, description="Provider API secret. Never committed; env only."
    )
    telephony_webhook_secret: Optional[str] = Field(
        None,
        description="Provider webhook signing secret (Twilio auth token). Required to accept provider webhooks.",
    )
    telephony_sip_domain: str = Field(
        "", description="SIP domain/trunk identifier for future SIP-trunk wiring (informational)."
    )
    telephony_public_base_url: str = Field(
        "",
        description="Public base URL of this gateway (e.g. https://voice.example.com). Used to reconstruct the signed webhook URL. Empty falls back to the incoming request URL.",
    )
    telephony_local_rtp_enabled: bool = Field(
        True,
        description="Enable the local RTP/UDP ingress for development and real SIP-phone media.",
    )
    telephony_local_rtp_host: str = Field(
        "127.0.0.1", description="Interface the local RTP listener binds to."
    )
    telephony_local_rtp_port: int = Field(
        10000, description="UDP port for inbound telephony RTP packets."
    )
    telephony_auto_accept_local: bool = Field(
        True,
        description="Auto-accept inbound local-RTP calls on first packet (development). Disable to require explicit accept.",
    )
    telephony_max_body_bytes: int = Field(
        65536, description="Maximum provider webhook body size in bytes."
    )
    telephony_rate_limit_per_min: int = Field(
        60,
        description="Per-source-IP rate limit (requests/minute) for telephony call-control and webhook endpoints.",
    )
    telephony_event_log_cap: int = Field(
        200, description="Maximum lifecycle events retained per live session for the telephony audit trail."
    )
    telephony_action_mode: Literal["detect-only"] = Field(
        "detect-only",
        description="Telephony enforcement posture. Only 'detect-only' is supported: risk decisions are recorded and exposed, the call is never terminated by VoiceShield. (Call termination requires a future ARI-control phase.)",
    )

    # Asterisk / ARI (WSL2 or Docker host; placeholders only, never commit secrets)
    asterisk_ari_url: str = Field(
        "http://127.0.0.1:8088/ari",
        description="Base URL of the Asterisk ARI interface (e.g. http://<wsl2-ip>:8088/ari).",
    )
    asterisk_ari_user: str = Field(
        "voiceshield", description="ARI username (must match asterisk/ari-secrets.conf on the Asterisk host)."
    )
    asterisk_ari_password: Optional[str] = Field(
        None, description="ARI password. Never committed; env only. Unset means ARI is not configured."
    )
    asterisk_ari_app: str = Field(
        "voiceshield", description="Stasis application name (must match extensions.conf Stasis() argument)."
    )
    asterisk_ari_timeout_s: float = Field(
        5.0, description="Timeout in seconds for Asterisk ARI REST calls."
    )

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
