"""Provider-neutral telephony ingress abstraction.

Transport layer only: telephony audio is normalized here and fed into the
existing real-time gateway/session (gateway/live_gateway.py), which owns
windowing, the AI pipeline, risk, actions, and audit.

No synthetic calls, scores, or audio exist anywhere in this package.
"""

from telephony.models import (
    TelephonySession,
    TelephonyState,
    TerminationReason,
)

__all__ = ["TelephonySession", "TelephonyState", "TerminationReason"]
