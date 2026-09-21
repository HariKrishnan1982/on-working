"""
Evidence fusion layer.

Acts purely as an aggregator: takes individual branch results and packages
them into a unified FusedEvidence structure.

Per architectural specification, NO decision, threshold, or inconsistency
logic resides here. All evaluation is performed deterministically by the Risk Engine.
"""

from schemas.models import FusedEvidence, IntentResult, SpeakerResult, SpoofResult


def fuse_evidence(
    spoof: SpoofResult,
    speaker: SpeakerResult,
    intent: IntentResult,
) -> FusedEvidence:
    """
    Assemble results from the three analysis branches into FusedEvidence.
    """
    assert spoof.session_id == speaker.session_id == intent.session_id, (
        f"Session ID mismatch: {spoof.session_id} vs {speaker.session_id} vs {intent.session_id}"
    )

    return FusedEvidence(
        session_id=spoof.session_id,
        spoof_result=spoof,
        speaker_result=speaker,
        intent_result=intent,
    )
