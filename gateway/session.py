"""Session management — creates CallSession objects from incoming call parameters."""

import hashlib

from schemas.models import CallSession, Language


def create_session(
    caller_id: str,
    audio_path: str,
    claimed_identity: str | None = None,
    language_hint: Language = Language.EN,
    metadata: dict | None = None,
) -> CallSession:
    """Create a new CallSession from incoming call parameters."""
    # For the stub: hash the path to produce a deterministic audio_hash
    audio_hash = hashlib.sha256(audio_path.encode()).hexdigest()
    return CallSession(
        caller_id=caller_id,
        claimed_identity=claimed_identity,
        audio_path_encrypted=audio_path,
        audio_hash_sha256=audio_hash,
        language_hint=language_hint,
        metadata=metadata or {},
    )
