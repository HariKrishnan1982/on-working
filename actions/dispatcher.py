"""Action dispatcher — maps RiskDecision to concrete actions."""

import logging

from schemas.models import ActionType, RiskDecision

logger = logging.getLogger(__name__)


def dispatch_action(decision: RiskDecision) -> dict:
    """
    Map a RiskDecision to a concrete action result.

    Returns a dict with action metadata (for logging / response enrichment).
    """
    handlers = {
        ActionType.ALLOW: _handle_allow,
        ActionType.FLAG: _handle_flag,
        ActionType.ESCALATE: _handle_escalate,
        ActionType.BLOCK: _handle_block,
    }
    handler = handlers[decision.action]
    result = handler(decision)
    logger.info("Action dispatched: %s for session %s", decision.action.value, decision.session_id)
    return result


def _handle_allow(d: RiskDecision) -> dict:
    return {"action": "ALLOW", "message": "Call permitted", "session_id": d.session_id}


def _handle_flag(d: RiskDecision) -> dict:
    return {
        "action": "FLAG",
        "message": "Call flagged for review",
        "session_id": d.session_id,
        "fired_rules": [r.rule_id for r in d.fired_rules],
    }


def _handle_escalate(d: RiskDecision) -> dict:
    return {
        "action": "ESCALATE",
        "message": "Call escalated to human analyst",
        "session_id": d.session_id,
        "fired_rules": [r.rule_id for r in d.fired_rules],
        "risk_level": d.risk_level.value,
    }


def _handle_block(d: RiskDecision) -> dict:
    return {
        "action": "BLOCK",
        "message": "Call blocked — suspected fraud",
        "session_id": d.session_id,
        "fired_rules": [r.rule_id for r in d.fired_rules],
        "risk_level": d.risk_level.value,
    }
