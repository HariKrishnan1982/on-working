"""
Deterministic risk engine evaluator.

Loads rules from a versioned YAML file and evaluates FusedEvidence
against them. Conditions are parsed through a validated Pydantic schema (no eval).
Highest risk level and most restrictive action win.
Ensures fail-closed behavior: degraded or failed branch states never yield ALLOW.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, List, Literal, Optional, Union

import yaml
from pydantic import BaseModel, Field

from schemas.models import (
    ActionType,
    BranchStatus,
    FiredRule,
    FusedEvidence,
    RiskDecision,
    RiskLevel,
)

# Severity hierarchies — higher number is more severe / restrictive
_RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}

_ACTION_ORDER: dict[ActionType, int] = {
    ActionType.ALLOW: 0,
    ActionType.FLAG: 1,
    ActionType.ESCALATE: 2,
    ActionType.BLOCK: 3,
}


# ─── Condition Schemas (Strictly Validated — No eval()) ───────────────────────


class SimpleCondition(BaseModel):
    field: str
    operator: Literal[">=", "<", "<=", ">", "==", "!=", "range"]
    value: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None


class BandCondition(BaseModel):
    type: Literal["band"] = "band"
    field: str
    band: str


class StatusCondition(BaseModel):
    type: Literal["status"] = "status"
    field: Optional[str] = None
    equals: Optional[str] = None
    match_any: Optional[List[dict]] = None


class CompoundCondition(BaseModel):
    type: Literal["compound"] = "compound"
    all: List[Union[SimpleCondition, BandCondition, StatusCondition, "CompoundCondition"]]


class RuleDefinition(BaseModel):
    id: str
    description: str
    condition: Union[CompoundCondition, BandCondition, StatusCondition, SimpleCondition]
    risk_level: RiskLevel
    action: ActionType


# ─── Evaluator Implementation ────────────────────────────────────────────────


class RiskEvaluator:
    """Deterministic, auditable Risk Engine evaluator."""

    def __init__(self, rules_path: Optional[Union[Path, str]] = None) -> None:
        if rules_path is None:
            self.rules_path = Path(__file__).parent / "rules.yaml"
        else:
            self.rules_path = Path(rules_path)

        with open(self.rules_path, "rb") as f:
            raw_bytes = f.read()

        # Compute deterministic SHA-256 hash of rules.yaml for audit trail
        self.rules_sha256: str = hashlib.sha256(raw_bytes).hexdigest()

        data = yaml.safe_load(raw_bytes.decode("utf-8"))
        self.version_tag: str = data.get("version", "0.0.0")
        self.rules_version: str = f"{self.version_tag}:{self.rules_sha256[:12]}"
        self.bands: dict[str, dict[str, dict[str, float]]] = data.get("bands", {})
        
        # Validate all rules through Pydantic schema
        raw_rules = data.get("rules", [])
        self.rules: list[RuleDefinition] = [RuleDefinition(**r) for r in raw_rules]

    @staticmethod
    def _extract_field(evidence: FusedEvidence, field_path: str) -> Any:
        """Safely extract nested attribute or dictionary key using dot notation."""
        curr: Any = evidence
        for part in field_path.split("."):
            if hasattr(curr, part):
                curr = getattr(curr, part)
            elif isinstance(curr, dict) and part in curr:
                curr = curr[part]
            else:
                return None
        return curr

    def _eval_simple(self, val: Any, cond: SimpleCondition) -> tuple[bool, str]:
        if val is None:
            return False, f"{cond.field} is None"
        if cond.operator == ">=":
            matched = float(val) >= float(cond.value or 0.0)
            return matched, f"{cond.field}={val} >= {cond.value}"
        elif cond.operator == "<":
            matched = float(val) < float(cond.value or 0.0)
            return matched, f"{cond.field}={val} < {cond.value}"
        elif cond.operator == "<=":
            matched = float(val) <= float(cond.value or 0.0)
            return matched, f"{cond.field}={val} <= {cond.value}"
        elif cond.operator == ">":
            matched = float(val) > float(cond.value or 0.0)
            return matched, f"{cond.field}={val} > {cond.value}"
        elif cond.operator == "==":
            matched = str(val) == str(cond.value)
            return matched, f"{cond.field}={val} == {cond.value}"
        elif cond.operator == "range":
            lo = float(cond.min if cond.min is not None else float("-inf"))
            hi = float(cond.max if cond.max is not None else float("inf"))
            matched = lo <= float(val) < hi
            return matched, f"{lo} <= {cond.field}={val} < {hi}"
        return False, "Unknown operator"

    def _eval_band(self, val: Any, cond: BandCondition) -> tuple[bool, str]:
        if val is None:
            return False, f"{cond.field} is None"
        # Find band definition from self.bands matching field suffix
        metric_name = cond.field.split(".")[-1]
        metric_bands = self.bands.get(metric_name)
        if not metric_bands or cond.band not in metric_bands:
            raise ValueError(f"Undefined band '{cond.band}' for metric '{metric_name}' in rules.yaml")

        bounds = metric_bands[cond.band]
        lo = float(bounds.get("min", float("-inf")))
        hi = float(bounds.get("max", float("inf")))
        matched = lo <= float(val) < hi
        return matched, f"{cond.field}={val} in band '{cond.band}' [{lo}, {hi})"

    def _eval_status(self, evidence: FusedEvidence, cond: StatusCondition) -> tuple[bool, str]:
        if cond.match_any:
            for sub in cond.match_any:
                field = sub.get("field", "")
                target = sub.get("equals", "")
                val = self._extract_field(evidence, field)
                val_str = val.value if hasattr(val, "value") else str(val)
                if val_str == target:
                    return True, f"{field}={val_str} equals '{target}'"
            return False, "No status match in match_any"

        val = self._extract_field(evidence, cond.field or "")
        val_str = val.value if hasattr(val, "value") else str(val)
        target = cond.equals or ""
        matched = val_str == target
        return matched, f"{cond.field}={val_str} equals '{target}'"

    def _eval_condition(self, evidence: FusedEvidence, cond: Any) -> tuple[bool, str]:
        """Dispatch evaluation without eval()."""
        if isinstance(cond, CompoundCondition):
            sub_summaries = []
            for sub in cond.all:
                matched, summary = self._eval_condition(evidence, sub)
                if not matched:
                    return False, ""
                sub_summaries.append(summary)
            return True, " AND ".join(sub_summaries)
        elif isinstance(cond, BandCondition):
            val = self._extract_field(evidence, cond.field)
            return self._eval_band(val, cond)
        elif isinstance(cond, StatusCondition):
            return self._eval_status(evidence, cond)
        elif isinstance(cond, SimpleCondition):
            val = self._extract_field(evidence, cond.field)
            return self._eval_simple(val, cond)
        elif isinstance(cond, dict):
            # Parse dict into corresponding model
            c_type = cond.get("type")
            if c_type == "compound":
                return self._eval_condition(evidence, CompoundCondition(**cond))
            elif c_type == "band":
                return self._eval_condition(evidence, BandCondition(**cond))
            elif c_type == "status":
                return self._eval_condition(evidence, StatusCondition(**cond))
            else:
                return self._eval_condition(evidence, SimpleCondition(**cond))
        return False, "Unsupported condition type"

    def evaluate(self, evidence: FusedEvidence) -> RiskDecision:
        """
        Deterministically evaluate FusedEvidence.

        Enforces FAIL-CLOSED:
        - If any branch status != OK, result must NEVER be ALLOW.
        - Highest risk level and most restrictive action win.
        """
        fired_rules: list[FiredRule] = []
        max_risk: RiskLevel = RiskLevel.LOW
        max_action: ActionType = ActionType.ALLOW

        for rule in self.rules:
            matched, summary = self._eval_condition(evidence, rule.condition)
            if matched:
                fired_rules.append(
                    FiredRule(
                        rule_id=rule.id,
                        description=rule.description,
                        risk_level=rule.risk_level,
                        action=rule.action,
                        condition_summary=summary,
                    )
                )
                if _RISK_ORDER[rule.risk_level] > _RISK_ORDER[max_risk]:
                    max_risk = rule.risk_level
                if _ACTION_ORDER[rule.action] > _ACTION_ORDER[max_action]:
                    max_action = rule.action

        # ─── Fail-Closed Verification ─────────────────────────────────────────
        branch_statuses = [
            ("antispoof", evidence.spoof_result.status),
            ("speaker", evidence.speaker_result.status),
            ("asr_intent", evidence.intent_result.status),
        ]
        degraded = [b for b, s in branch_statuses if s != BranchStatus.OK]

        if degraded:
            # If any branch is degraded, action MUST NOT be ALLOW
            if max_action == ActionType.ALLOW:
                max_action = ActionType.FLAG
            if max_risk == RiskLevel.LOW:
                max_risk = RiskLevel.MEDIUM

        reasons = [
            f"[{r.rule_id}] {r.description} ({r.condition_summary})"
            for r in fired_rules
        ]
        if degraded:
            for branch, status in branch_statuses:
                if status != BranchStatus.OK:
                    reasons.append(f"[FAIL_CLOSED_GUARD] Degraded evidence from '{branch}' branch: status={status.value}")

        model_versions = {
            "antispoof": evidence.spoof_result.model_version,
            "speaker": evidence.speaker_result.model_version,
            "asr_intent": evidence.intent_result.model_version,
        }

        return RiskDecision(
            session_id=evidence.session_id,
            risk_level=max_risk,
            action=max_action,
            fired_rules=fired_rules,
            reasons=reasons,
            rules_version=self.rules_version,
            model_versions=model_versions,
            fused_evidence=evidence,
        )
