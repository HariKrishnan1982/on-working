"""
Privacy-Preserving Speaker Enrollment Store.

Adheres strictly to the ConsentRegistry privacy architecture:
1. Storage is keyed by HMAC-SHA256 pseudonyms (subject_ref) derived from
   compute_pseudonymous_subject_ref(speaker_id, settings.vfd_hmac_secret).
   No raw PII, phone numbers, or cleartext speaker names are used as file names.
2. Biometric voiceprint embeddings are encrypted at rest using Fernet authenticated
   symmetric encryption derived from the off-chain secret salt.
3. Only the SHA-256 hash of the embedding and the storage reference pointer
   are stored for audit trail provenance, matching the SpeakerEnrollment schema.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import torch
from cryptography.fernet import Fernet

from configs.settings import settings
from schemas.hash_utils import canonical_json_str, compute_pseudonymous_subject_ref
from schemas.models import ConsentRecord, SpeakerEnrollment

logger = logging.getLogger(__name__)

DEFAULT_ENROLLMENT_DIR = Path("storage/enrollments")


def _derive_fernet_key(secret: str) -> bytes:
    """Derive 32-byte URL-safe base64 Fernet key from off-chain secret salt."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


class SpeakerEnrollmentStore:
    """
    Manages pseudonymous and encrypted storage of biometric voiceprint profiles.
    """

    def __init__(
        self,
        storage_dir: Path = DEFAULT_ENROLLMENT_DIR,
        hmac_secret: Optional[str] = None,
    ) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.hmac_secret = hmac_secret or settings.vfd_hmac_secret
        self._fernet = Fernet(_derive_fernet_key(self.hmac_secret))
        # In-memory cache for fast lookup: subject_ref -> torch.Tensor
        self._embedding_cache: Dict[str, torch.Tensor] = {}
        self._enrollment_cache: Dict[str, SpeakerEnrollment] = {}

    def get_subject_ref(self, speaker_id: str) -> str:
        """Derive 64-character pseudonymous HMAC-SHA256 reference matching ConsentRegistry."""
        return compute_pseudonymous_subject_ref(speaker_id, self.hmac_secret)

    def enroll_speaker(
        self,
        speaker_id: str,
        embedding: torch.Tensor,
        consent: ConsentRecord,
    ) -> SpeakerEnrollment:
        """
        Enroll a speaker profile:
        - Keys storage by HMAC-SHA256 pseudonym.
        - Encrypts the 192-dim embedding tensor at rest.
        - Stores metadata and returns SpeakerEnrollment contract.
        """
        subject_ref = self.get_subject_ref(speaker_id)

        # 1. Compute SHA-256 hash of raw embedding tensor
        emb_cpu = embedding.detach().cpu().float().squeeze()
        emb_bytes_raw = emb_cpu.numpy().tobytes()
        emb_hash = hashlib.sha256(emb_bytes_raw).hexdigest()

        # 2. Serialize tensor and encrypt with Fernet
        buf = io.BytesIO()
        torch.save(emb_cpu, buf)
        encrypted_bytes = self._fernet.encrypt(buf.getvalue())

        # 3. Write encrypted tensor to disk under pseudonymous filename
        enc_path = self.storage_dir / f"{subject_ref}.enc"
        enc_path.write_bytes(encrypted_bytes)

        # 4. Construct SpeakerEnrollment contract
        enrollment = SpeakerEnrollment(
            speaker_id=speaker_id,
            consent=consent,
            embedding_ref=str(enc_path.as_posix()),
            embedding_hash_sha256=emb_hash,
            created_at=datetime.now(timezone.utc),
        )

        # 5. Persist pseudonymous metadata record (JSON)
        meta_dict = {
            "subject_ref": subject_ref,
            "embedding_ref": str(enc_path.as_posix()),
            "embedding_hash_sha256": emb_hash,
            "consent_id": consent.consent_id,
            "consent_scope": consent.consent_scope,
            "consent_timestamp": consent.consent_timestamp.isoformat(),
            "created_at": enrollment.created_at.isoformat(),
        }
        meta_path = self.storage_dir / f"{subject_ref}.json"
        meta_path.write_text(canonical_json_str(meta_dict), encoding="utf-8")

        # 6. Update cache
        self._embedding_cache[subject_ref] = emb_cpu
        self._enrollment_cache[subject_ref] = enrollment

        logger.info("Enrolled speaker profile with subjectRef %s", subject_ref[:12] + "...")
        return enrollment

    def is_enrolled(self, speaker_id: str) -> bool:
        """Check if speaker has an active enrolled biometric profile."""
        if not speaker_id or speaker_id.strip() == "" or speaker_id == "unknown":
            return False
        subject_ref = self.get_subject_ref(speaker_id)
        if subject_ref in self._embedding_cache:
            return True
        enc_path = self.storage_dir / f"{subject_ref}.enc"
        return enc_path.is_file()

    def get_embedding(self, speaker_id: str) -> Optional[torch.Tensor]:
        """Retrieve and decrypt the enrolled speaker embedding tensor."""
        if not self.is_enrolled(speaker_id):
            return None

        subject_ref = self.get_subject_ref(speaker_id)
        if subject_ref in self._embedding_cache:
            return self._embedding_cache[subject_ref]

        enc_path = self.storage_dir / f"{subject_ref}.enc"
        if not enc_path.is_file():
            return None

        try:
            encrypted_bytes = enc_path.read_bytes()
            decrypted_bytes = self._fernet.decrypt(encrypted_bytes)
            buf = io.BytesIO(decrypted_bytes)
            emb = torch.load(buf, map_location="cpu")
            self._embedding_cache[subject_ref] = emb
            return emb
        except Exception as e:
            logger.error("Failed to decrypt embedding for subjectRef %s: %s", subject_ref, e)
            return None

    def get_enrollment(self, speaker_id: str) -> Optional[SpeakerEnrollment]:
        """Retrieve the SpeakerEnrollment metadata record."""
        if not self.is_enrolled(speaker_id):
            return None

        subject_ref = self.get_subject_ref(speaker_id)
        if subject_ref in self._enrollment_cache:
            return self._enrollment_cache[subject_ref]

        meta_path = self.storage_dir / f"{subject_ref}.json"
        if not meta_path.is_file():
            return None

        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            consent = ConsentRecord(
                consent_id=data["consent_id"],
                speaker_id=speaker_id,
                consent_timestamp=datetime.fromisoformat(data["consent_timestamp"]),
                consent_scope=data.get("consent_scope", "voice_biometrics_verification"),
                consented_by=speaker_id,
            )
            enrollment = SpeakerEnrollment(
                speaker_id=speaker_id,
                consent=consent,
                embedding_ref=data["embedding_ref"],
                embedding_hash_sha256=data["embedding_hash_sha256"],
                created_at=datetime.fromisoformat(data["created_at"]),
            )
            self._enrollment_cache[subject_ref] = enrollment
            return enrollment
        except Exception as e:
            logger.error("Failed to load enrollment metadata for %s: %s", subject_ref, e)
            return None

    def clear(self) -> None:
        """Clear cache and disk store (primarily for test isolation)."""
        self._embedding_cache.clear()
        self._enrollment_cache.clear()
        if self.storage_dir.exists():
            for p in self.storage_dir.glob("*.enc"):
                p.unlink(missing_ok=True)
            for p in self.storage_dir.glob("*.json"):
                p.unlink(missing_ok=True)


# Global singleton enrollment store
_GLOBAL_STORE: Optional[SpeakerEnrollmentStore] = None


def get_enrollment_store() -> SpeakerEnrollmentStore:
    """Return singleton SpeakerEnrollmentStore instance."""
    global _GLOBAL_STORE
    if _GLOBAL_STORE is None:
        _GLOBAL_STORE = SpeakerEnrollmentStore()
    return _GLOBAL_STORE
