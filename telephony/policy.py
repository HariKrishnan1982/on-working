"""
Telephony action policy — detect-only enforcement posture.

The shared PipelineService + action dispatcher decide ALLOW/FLAG/ESCALATE/
BLOCK for every analyzed call. For telephony legs, VoiceShield is a passive
tap in the media path: there is currently NO mechanism that can lawfully
terminate the underlying PBX/carrier call (that requires a future ARI/AMI
control phase with explicit operator opt-in).

Therefore, regardless of the decided action, this policy:

- records the decision (ops store + audit chain via the shared finalize path),
- exposes it on the telephony snapshot (`latest_action`) and UI,
- NEVER ends, redirects, or otherwise disturbs the live call.

`settings.telephony_action_mode` is a Literal["detect-only"]: any other value
fails configuration validation loudly instead of silently changing behavior.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from configs.settings import settings

logger = logging.getLogger(__name__)

# Audit-facing names for the telephony lifecycle (operational trail, not the
# on-chain ledger — only the final RiskDecision hash is anchored).
AUDIT_EVENT_CALL_RECEIVED = "CALL_RECEIVED"
AUDIT_EVENT_CALL_ACCEPTED = "CALL_ACCEPTED"
AUDIT_EVENT_MEDIA_CONNECTED = "MEDIA_CONNECTED"
AUDIT_EVENT_AUDIO_RECEIVING = "AUDIO_RECEIVING"
AUDIT_EVENT_ANALYSIS_STARTED = "ANALYSIS_STARTED"
AUDIT_EVENT_ANALYSIS_COMPLETED = "ANALYSIS_COMPLETED"
AUDIT_EVENT_RISK_UPDATED = "RISK_UPDATED"
AUDIT_EVENT_ACTION_TAKEN = "ACTION_TAKEN"
AUDIT_EVENT_CALL_ENDED = "CALL_ENDED"
AUDIT_EVENT_CALL_FAILED = "CALL_FAILED"

# Live gateway event type -> audit-facing name (unmapped types keep their own name).
EVENT_TO_AUDIT = {
    "telephony.call.received": AUDIT_EVENT_CALL_RECEIVED,
    "telephony.call.accepted": AUDIT_EVENT_CALL_ACCEPTED,
    "telephony.media.connected": AUDIT_EVENT_MEDIA_CONNECTED,
    "telephony.audio.receiving": AUDIT_EVENT_AUDIO_RECEIVING,
    "audio.receiving": AUDIT_EVENT_AUDIO_RECEIVING,
    "analysis.started": AUDIT_EVENT_ANALYSIS_STARTED,
    "analysis.completed": AUDIT_EVENT_ANALYSIS_COMPLETED,
    "action.taken": AUDIT_EVENT_ACTION_TAKEN,
    "telephony.call.ended": AUDIT_EVENT_CALL_ENDED,
    "session.ended": AUDIT_EVENT_CALL_ENDED,
    "telephony.call.failed": AUDIT_EVENT_CALL_FAILED,
    "session.error": AUDIT_EVENT_CALL_FAILED,
}


def resolve_call_action(action: str, session_id: str) -> Dict[str, Any]:
    """Apply the telephony enforcement posture to a decided action.

    Returns a resolution record; never touches call state. BLOCK (or any
    other action) is recorded and exposed, the call is preserved.
    """
    mode = settings.telephony_action_mode
    if mode != "detect-only":  # pragma: no cover - guarded by Literal validation
        raise ValueError(f"Unsupported telephony_action_mode: {mode!r}")
    logger.info(
        "telephony action resolved id=%s action=%s mode=%s enforced=%s",
        session_id,
        action,
        mode,
        False,
    )
    return {
        "mode": mode,
        "recorded_action": action,
        "enforced": False,
        "call_preserved": True,
    }
