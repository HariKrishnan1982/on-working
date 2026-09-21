"""
Privacy-Preserving Transcript Store.

Adheres strictly to the project zero-PII privacy architecture:
1. Spoken transcripts (which may contain spoken account numbers, OTPs, or PII)
   are NEVER stored in plaintext on disk or written to the blockchain ledger.
2. Transcripts cached for authorized auditing are encrypted at rest using
   Fernet authenticated symmetric encryption (AES-128-CBC + HMAC-SHA256)
   derived from the off-chain secret salt (settings.vfd_hmac_secret).
3. Files on disk are keyed strictly by the SHA-256 hash of the transcript
   (e.g., storage/transcripts/{transcript_hash}.enc).
4. Only the transcript_hash_sha256 and transcript_ref reach the audit trail.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from pathlib import Path
from typing import Optional, Tuple

from cryptography.fernet import Fernet

from configs.settings import settings

logger = logging.getLogger(__name__)

DEFAULT_TRANSCRIPT_DIR = Path("storage/transcripts")


def _derive_fernet_key(secret: str) -> bytes:
    """Derive 32-byte URL-safe base64 Fernet key from off-chain secret salt."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


class TranscriptStore:
    """
    Manages encrypted storage and retrieval of speech transcriptions at rest.
    """

    def __init__(
        self,
        storage_dir: Path = DEFAULT_TRANSCRIPT_DIR,
        hmac_secret: Optional[str] = None,
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.hmac_secret = hmac_secret or settings.vfd_hmac_secret
        self._fernet = Fernet(_derive_fernet_key(self.hmac_secret))

    def store_transcript(self, transcript: str) -> Tuple[str, str]:
        """
        Encrypt and persist transcript at rest under its SHA-256 hash.

        Returns:
            Tuple[str, str]: (transcript_hash_sha256, transcript_ref)
        """
        raw_bytes = transcript.strip().encode("utf-8")
        transcript_hash = hashlib.sha256(raw_bytes).hexdigest()

        encrypted_bytes = self._fernet.encrypt(raw_bytes)
        enc_path = self.storage_dir / f"{transcript_hash}.enc"
        enc_path.write_bytes(encrypted_bytes)

        ref_str = str(enc_path.as_posix())
        return transcript_hash, ref_str

    def get_transcript(self, transcript_hash: str) -> Optional[str]:
        """Decrypt and return transcript given its SHA-256 hash."""
        enc_path = self.storage_dir / f"{transcript_hash}.enc"
        if not enc_path.is_file():
            return None
        try:
            decrypted = self._fernet.decrypt(enc_path.read_bytes())
            return decrypted.decode("utf-8")
        except Exception as e:
            logger.error("Failed to decrypt transcript %s: %s", transcript_hash[:12], e)
            return None

    def clear(self) -> None:
        """Clear store directory (primarily for test isolation)."""
        if self.storage_dir.exists():
            for p in self.storage_dir.glob("*.enc"):
                p.unlink(missing_ok=True)


_GLOBAL_TRANSCRIPT_STORE: Optional[TranscriptStore] = None


def get_transcript_store() -> TranscriptStore:
    """Return singleton TranscriptStore instance."""
    global _GLOBAL_TRANSCRIPT_STORE
    if _GLOBAL_TRANSCRIPT_STORE is None:
        _GLOBAL_TRANSCRIPT_STORE = TranscriptStore()
    return _GLOBAL_TRANSCRIPT_STORE
