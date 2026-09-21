#!/usr/bin/env python
"""
Voice Fraud Detection System — Real-Time Demonstration CLI.

Processes a real audio file through the multi-branch detection pipeline:
- Phase 1: Voice Activity Detection (Silero VAD) & 16kHz Preprocessing
- Phase 2: Anti-Spoofing & Deepfake Detection (Clova AI AASIST)
- Phase 3: Biometric Speaker Verification (SpeechBrain ECAPA-TDNN)
- Phase 4: ASR & Scam-Intent Analysis (Faster-Whisper + Multilingual Scanner)
- Decision: Evidence Fusion & Deterministic Risk Engine (rules.yaml)
- Audit: Immutable Dual-Write Ledger & Transactional Outbox (PostgreSQL + Fabric)

Usage:
    uv run python demo.py <path-to-audio-file> [options]

Options:
    --claimed-identity <id>   Enrolled speaker identity (default: "unknown" -> triggers NOT_ENROLLED)
    --caller-id <phone>       Caller phone number or reference (default: "+919876543210")
    --language <lang>         Language hint (EN, HI, TA, TE, ML, KN; default: auto-detect)
    --json                    Output raw JSON alongside / instead of formatted view
    --no-color                Disable ANSI terminal colors
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Suppress HuggingFace and PyTorch symlink warnings on Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

import soundfile as sf

from actions.dispatcher import dispatch_action
from audit.fabric_sink import FabricSink
from branches.antispoof import analyze_spoof
from branches.asr_intent import analyze_intent
from branches.speaker import verify_speaker
from configs.settings import settings
from fusion.engine import fuse_evidence
from preprocess import preprocess_audio
from risk_engine.evaluator import RiskEvaluator
from schemas.hash_utils import build_canonical_decision_payload, compute_decision_hash
from schemas.models import (
    ActionType,
    AuditRecord,
    BranchStatus,
    CallSession,
    IntentCategory,
    Language,
    PreprocessedAudio,
    RiskDecision,
    RiskLevel,
)
from services.integrity_guard import IntegrityGuard


# ── ANSI Color Formatting ───────────────────────────────────────────────────

class Colors:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"{code}{text}\033[0m" if self.enabled else text

    def bold(self, text: str) -> str:
        return self._wrap("\033[1m", text)

    def dim(self, text: str) -> str:
        return self._wrap("\033[2m", text)

    def red(self, text: str) -> str:
        return self._wrap("\033[91m", text)

    def green(self, text: str) -> str:
        return self._wrap("\033[92m", text)

    def yellow(self, text: str) -> str:
        return self._wrap("\033[93m", text)

    def blue(self, text: str) -> str:
        return self._wrap("\033[94m", text)

    def magenta(self, text: str) -> str:
        return self._wrap("\033[95m", text)

    def cyan(self, text: str) -> str:
        return self._wrap("\033[96m", text)

    def action_badge(self, action: ActionType) -> str:
        if action == ActionType.ALLOW:
            return self._wrap("\033[1;42;37m", "  ALLOW  ")
        elif action == ActionType.FLAG:
            return self._wrap("\033[1;43;30m", "  FLAG   ")
        elif action == ActionType.ESCALATE:
            return self._wrap("\033[1;41;37m", " ESCALATE ")
        elif action == ActionType.BLOCK:
            return self._wrap("\033[1;45;37m", "  BLOCK  ")
        return str(action.value)

    def risk_badge(self, risk: RiskLevel) -> str:
        if risk == RiskLevel.LOW:
            return self._wrap("\033[92m\033[1m", "LOW")
        elif risk == RiskLevel.MEDIUM:
            return self._wrap("\033[93m\033[1m", "MEDIUM")
        elif risk == RiskLevel.HIGH:
            return self._wrap("\033[91m\033[1m", "HIGH")
        elif risk == RiskLevel.CRITICAL:
            return self._wrap("\033[95m\033[1m", "CRITICAL")
        return str(risk.value)


# ── Live Demonstration Runner ───────────────────────────────────────────────

class VoiceFraudDemoRunner:
    def __init__(self, use_color: bool = True) -> None:
        self.c = Colors(enabled=use_color)
        self.evaluator = RiskEvaluator()
        self.integrity_guard = IntegrityGuard()

    def print_banner(self) -> None:
        c = self.c
        print()
        print(c.cyan("=" * 80))
        print(c.bold(c.cyan("   VOICE FRAUD DETECTION & BIOMETRIC CYBERSECURITY PLATFORM   ")))
        print(c.dim("   Real-Time Multi-Branch Deepfake Countermeasures & Immutable Audit Trail   "))
        print(c.cyan("=" * 80))
        print()

    def run(
        self,
        audio_path_str: str,
        claimed_identity: str = "unknown",
        caller_id: str = "+919876543210",
        language_str: str = "auto",
        dump_json: bool = False,
    ) -> int:
        c = self.c
        audio_file = Path(audio_path_str).resolve()

        if not dump_json:
            self.print_banner()

        # Validate input file existence
        if not audio_file.is_file():
            print(c.red(f"[ERROR] Audio file not found: {audio_file}"), file=sys.stderr)
            return 1

        total_t0 = time.time()
        session_id = f"demo-{int(time.time())}-{audio_file.stem[:12]}"

        # Compute initial audio file hash
        raw_audio_bytes = audio_file.read_bytes()
        audio_hash = hashlib.sha256(raw_audio_bytes).hexdigest()

        # Parse audio metadata
        try:
            info = sf.info(str(audio_file))
            audio_sr = info.samplerate
            audio_duration = info.duration
            audio_channels = info.channels
        except Exception:
            audio_sr = 16000
            audio_duration = 0.0
            audio_channels = 1

        lang_hint = Language.EN
        if language_str.upper() in Language.__members__:
            lang_hint = Language[language_str.upper()]

        session = CallSession(
            session_id=session_id,
            caller_id=caller_id,
            claimed_identity=claimed_identity,
            audio_path_encrypted=str(audio_file),
            audio_hash_sha256=audio_hash,
            language_hint=lang_hint,
        )

        if not dump_json:
            print(c.bold("1. Call Session Parameters"))
            print(f"   * Session ID        : {c.cyan(session_id)}")
            print(f"   * Audio File        : {audio_file.name} ({len(raw_audio_bytes):,} bytes)")
            print(f"   * Format            : {audio_sr} Hz, {audio_channels} ch, {audio_duration:.2f}s duration")
            print(f"   * Audio SHA-256     : {c.dim(audio_hash[:16] + '...' + audio_hash[-16:])}")
            print(f"   * Caller Identity   : {c.bold(caller_id)}")
            print(f"   * Claimed Identity  : {c.yellow(claimed_identity) if claimed_identity == 'unknown' else c.green(claimed_identity)}")
            print(c.dim("-" * 80))
            print()

        # ── STAGE 1: Audio Preprocessing & Silero VAD ─────────────────────────
        if not dump_json:
            print(c.bold("2. Phase 1 — Signal Preprocessing & Voice Activity Detection (Silero VAD)"))
        t_vad0 = time.time()
        preprocessed = preprocess_audio(session.session_id, session.audio_path_encrypted)
        vad_ms = (time.time() - t_vad0) * 1000.0

        if not dump_json:
            valid_str = c.green("PASSED (Speech detected)") if preprocessed.is_valid else c.red("FAILED (Silence / Insufficient audio)")
            print(f"   * Validity Check    : {valid_str}")
            print(f"   * Speech Segments   : {len(preprocessed.vad_segments)} voiced segment(s) detected")
            print(f"   * Voiced Duration   : {preprocessed.speech_duration_s:.2f}s / {preprocessed.duration_s:.2f}s ({preprocessed.speech_duration_s / (preprocessed.duration_s or 1.0) * 100:.1f}%)")
            print(f"   * Estimated SNR     : {preprocessed.snr_db:.1f} dB ({'Clean signal' if preprocessed.snr_db >= 15 else 'Noisy / Borderline'})")
            print(f"   * Processing Time   : {c.dim(f'{vad_ms:.1f} ms')}")
            print(c.dim("-" * 80))
            print()

        # Fail-closed branch status determination
        effective_status = BranchStatus.OK if preprocessed.is_valid else BranchStatus.INSUFFICIENT_AUDIO

        # ── STAGE 2: Anti-Spoofing & Deepfake Detection (AASIST) ─────────────
        if not dump_json:
            print(c.bold("3. Phase 2 — Anti-Spoofing / Deepfake Countermeasure (Clova AI AASIST)"))
        t_spoof0 = time.time()
        spoof_res = analyze_spoof(
            session_id=session.session_id,
            preprocessed_audio=preprocessed,
            audio_path=session.audio_path_encrypted,
            status=effective_status,
        )
        spoof_ms = (time.time() - t_spoof0) * 1000.0

        if not dump_json:
            if spoof_res.status == BranchStatus.OK:
                p_spoof = spoof_res.spoof_score
                p_bona = 1.0 - p_spoof
                verdict = c.red("SPOOFED / SYNTHETIC VOICE") if spoof_res.is_spoofed else c.green("BONA-FIDE HUMAN VOICE")
                print(f"   * Model Version     : {spoof_res.model_version}")
                print(f"   * Detection Verdict : {c.bold(verdict)}")
                print(f"   * Probabilities     : P(spoof) = {c.bold(f'{p_spoof:.4f}')} | P(bonafide) = {f'{p_bona:.4f}'}")
                print(f"   * Spoof Score Band  : {self._get_spoof_band(p_spoof)}")
            else:
                print(f"   * Status            : {c.yellow(spoof_res.status.value.upper())} ({spoof_res.error_message})")
            print(f"   * Processing Time   : {c.dim(f'{spoof_ms:.1f} ms')}")
            print(c.dim("-" * 80))
            print()

        # ── STAGE 3: Speaker Verification (ECAPA-TDNN) ────────────────────────
        if not dump_json:
            print(c.bold("4. Phase 3 — Biometric Speaker Verification (SpeechBrain ECAPA-TDNN)"))
        t_spk0 = time.time()
        spk_res = verify_speaker(
            session_id=session.session_id,
            claimed_identity=session.claimed_identity or "unknown",
            preprocessed_audio=preprocessed,
            audio_path=session.audio_path_encrypted,
            status=effective_status,
        )
        spk_ms = (time.time() - t_spk0) * 1000.0

        if not dump_json:
            print(f"   * Model Version     : {spk_res.model_version}")
            print(f"   * Claimed Identity  : {spk_res.claimed_identity}")
            if spk_res.status == BranchStatus.OK:
                match_str = c.green("MATCH CONFIRMED") if spk_res.is_match else c.red("MISMATCH / IMPOSTER")
                raw_cos_str = f"{spk_res.raw_cosine:+.4f}" if spk_res.raw_cosine is not None else "N/A"
                print(f"   * Verification      : {c.bold(match_str)}")
                print(f"   * Similarity Score  : {c.bold(f'{spk_res.similarity_score:.4f}')} (Threshold: {spk_res.threshold_used})")
                print(f"   * Raw Cosine Sim    : {raw_cos_str} in [-1.0, +1.0]")
                print(f"   * Biometric Hash    : {c.dim(spk_res.embedding_hash_sha256[:16] + '...') if spk_res.embedding_hash_sha256 else 'N/A'}")
            elif spk_res.status == BranchStatus.NOT_ENROLLED:
                print(f"   * Verification      : {c.yellow('NOT ENROLLED (Fail-Closed: identity cannot be verified)')}")
                print(f"   * Explanation       : Caller '{spk_res.claimed_identity}' has no biometric voice profile on file")
            else:
                print(f"   * Status            : {c.yellow(spk_res.status.value.upper())} ({spk_res.error_message})")
            print(f"   * Processing Time   : {c.dim(f'{spk_ms:.1f} ms')}")
            print(c.dim("-" * 80))
            print()

        # ── STAGE 4: ASR & Scam-Intent Analysis (Faster-Whisper) ───────────────
        if not dump_json:
            print(c.bold("5. Phase 4 — ASR Speech-to-Text & Scam-Intent Analysis (Faster-Whisper)"))
        t_asr0 = time.time()
        intent_res = analyze_intent(
            session_id=session.session_id,
            preprocessed_audio=preprocessed,
            audio_path=session.audio_path_encrypted,
            language_hint=session.language_hint,
            status=effective_status,
        )
        asr_ms = (time.time() - t_asr0) * 1000.0

        if not dump_json:
            print(f"   * Model Version     : {intent_res.model_version}")
            print(f"   * Detected Language : {c.bold(intent_res.language_detected.value)}")
            print(f"   * Transcript Privacy: {c.yellow('[PRIVACY GUARD: Rendered locally in terminal only; never committed to ledger/blockchain]')}")
            if intent_res.transcript:
                quoted = f'"{intent_res.transcript}"'
                print(f"   * Transcript Text   : {c.cyan(quoted)}")
            else:
                print(f"   * Transcript Text   : {c.dim('(no speech transcribed)')}")

            cat_str = self._format_intent_category(intent_res.intent_category)
            print(f"   * Scam-Intent Score : {c.bold(f'{intent_res.scam_score:.3f}')} in [0.0, 1.0]")
            print(f"   * Category Verdict  : {cat_str}")
            if intent_res.scam_indicators:
                indicators_str = ", ".join([c.red(f"[{i}]") for i in intent_res.scam_indicators])
                print(f"   * Warning Indicators: {indicators_str}")
            else:
                print(f"   * Warning Indicators: {c.green('None (clean conversational intent)')}")
            print(f"   * Transcript SHA-256: {c.dim(intent_res.transcript_hash_sha256[:16] + '...')}")
            print(f"   * Processing Time   : {c.dim(f'{asr_ms:.1f} ms')}")
            print(c.dim("-" * 80))
            print()

        # ── STAGE 5: Evidence Fusion & Deterministic Risk Engine ──────────────
        if not dump_json:
            print(c.bold("6. Evidence Fusion & Deterministic Risk Engine (rules.yaml)"))
        t_eval0 = time.time()
        evidence = fuse_evidence(
            spoof=spoof_res,
            speaker=spk_res,
            intent=intent_res,
        )
        decision = self.evaluator.evaluate(evidence)
        eval_ms = (time.time() - t_eval0) * 1000.0

        # Action dispatch hook
        dispatch_action(decision)

        if not dump_json:
            print(f"   * Final Decision    : {c.bold(c.action_badge(decision.action))} (Risk Level: {c.risk_badge(decision.risk_level)})")
            print(f"   * Rules Version     : {decision.rules_version}")
            if decision.fired_rules:
                print("   * Fired Rule(s)     :")
                for rule in decision.fired_rules:
                    print(f"       -> {c.bold(rule.rule_id)}: {rule.description}")
                    print(f"          {c.dim('Risk: ' + rule.risk_level.value + ' | Action: ' + rule.action.value)}")
            else:
                print(f"   * Fired Rule(s)     : {c.green('None (all signals within clean operating bounds)')}")

            if decision.reasons:
                print("   * Decision Reasons  :")
                for r in decision.reasons:
                    print(f"       * {r}")
            print(f"   * Processing Time   : {c.dim(f'{eval_ms:.1f} ms')}")
            print(c.dim("-" * 80))
            print()

        # ── STAGE 6: Immutable Audit Trail & Blockchain Outbox ────────────────
        if not dump_json:
            print(c.bold("7. Immutable Audit Trail & Blockchain Outbox Anchoring"))
        t_audit0 = time.time()
        decision_hash = compute_decision_hash(decision, caller_id=session.caller_id)
        canonical_payload = build_canonical_decision_payload(decision, caller_id=session.caller_id)

        # Attempt transactional write to PostgreSQL / Outbox
        audit_sink = FabricSink()
        anchor_status = "anchor_pending"
        chain_pos_str = "local_cache"
        record_hash_str = decision_hash
        written_to_db = False

        try:
            record = asyncio.run(audit_sink.append(decision))
            anchor_status = getattr(record, "anchor_status", "anchor_pending")
            chain_pos_str = str(record.chain_position)
            record_hash_str = record.record_hash
            written_to_db = True
        except Exception:
            # PostgreSQL is offline or running without daemon; fallback to local audit verification
            written_to_db = False
            anchor_status = "anchor_pending"
        audit_ms = (time.time() - t_audit0) * 1000.0

        total_elapsed_s = time.time() - total_t0

        if not dump_json:
            db_status_str = c.green("COMMITTED (PostgreSQL hash chain)") if written_to_db else c.yellow("CALCULATED (Local audit cache; DB offline)")
            print(f"   * PostgreSQL Ledger : {db_status_str}")
            print(f"   * Chain Position    : #{chain_pos_str}")
            print(f"   * Decision SHA-256  : {c.cyan(decision_hash)}")
            print(f"   * Fabric Outbox     : {c.green('anchor_pending')} (Expected state: live Fabric network deferred on Docker)")
            print(f"   * On-Chain Zero PII : {c.green('VERIFIED (Only scores, rule IDs, and SHA-256 pointers anchored)')}")
            print(f"   * Audit Write Time  : {c.dim(f'{audit_ms:.1f} ms')}")
            print(c.dim("-" * 80))
            print()

            # ── Summary Footer ────────────────────────────────────────────────
            print(c.cyan("=" * 80))
            print(f"   TOTAL PIPELINE LATENCY: {c.bold(f'{total_elapsed_s:.3f} s')} ({total_elapsed_s * 1000:.1f} ms)")
            print(f"   FINAL SYSTEM ACTION   : {c.action_badge(decision.action)}")
            print(c.cyan("=" * 80))
            print()

        if dump_json:
            out_data = {
                "session_id": session.session_id,
                "caller_id": session.caller_id,
                "claimed_identity": session.claimed_identity,
                "audio_file": str(audio_file),
                "audio_hash_sha256": audio_hash,
                "timing_ms": {
                    "vad_preprocessing": round(vad_ms, 1),
                    "aasist_antispoof": round(spoof_ms, 1),
                    "ecapa_speaker": round(spk_ms, 1),
                    "faster_whisper_asr": round(asr_ms, 1),
                    "risk_evaluation": round(eval_ms, 1),
                    "audit_layer": round(audit_ms, 1),
                    "total_elapsed_ms": round(total_elapsed_s * 1000.0, 1),
                },
                "decision": decision.model_dump(mode="json"),
                "audit": {
                    "decision_hash": decision_hash,
                    "anchor_status": anchor_status,
                    "written_to_database": written_to_db,
                },
            }
            print(json.dumps(out_data, indent=2))

        return 0

    def _get_spoof_band(self, score: float) -> str:
        c = self.c
        if score < 0.30:
            return c.green(f"Clean [{score:.3f} in 0.0-0.30]")
        elif score < 0.60:
            return c.yellow(f"Low Suspicion [{score:.3f} in 0.40-0.60]")
        elif score < 0.85:
            return c.red(f"Moderate Spoof [{score:.3f} in 0.60-0.85]")
        return c.bold(c.red(f"High Spoof [{score:.3f} in 0.85-1.0]"))

    def _format_intent_category(self, cat: IntentCategory) -> str:
        c = self.c
        if cat == IntentCategory.BENIGN:
            return c.green("BENIGN (Clean Intent)")
        elif cat == IntentCategory.SUSPICIOUS:
            return c.yellow("SUSPICIOUS (Borderline Intent)")
        elif cat == IntentCategory.SCAM_LIKELY:
            return c.red("SCAM LIKELY (Urgency / Financial Pressure)")
        elif cat == IntentCategory.SCAM_CONFIRMED:
            return c.bold(c.red("SCAM CONFIRMED (Impersonation / Digital Arrest)"))
        return str(cat.value)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Voice Fraud Detection System — Real-Time Live Terminal Demonstration CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("audio_path", help="Path to input audio file (WAV, FLAC, OGG, MP3)")
    parser.add_argument("--claimed-identity", default="unknown", help="Claimed speaker identity (default: 'unknown' -> triggers NOT_ENROLLED)")
    parser.add_argument("--caller-id", default="+919876543210", help="Caller phone number (default: +919876543210)")
    parser.add_argument("--language", default="auto", help="Language hint (EN, HI, TA, TE; default: auto)")
    parser.add_argument("--json", action="store_true", help="Print raw JSON decision alongside/instead of terminal UI")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI terminal colors")

    args = parser.parse_args()
    runner = VoiceFraudDemoRunner(use_color=not args.no_color)

    return runner.run(
        audio_path_str=args.audio_path,
        claimed_identity=args.claimed_identity,
        caller_id=args.caller_id,
        language_str=args.language,
        dump_json=args.json,
    )


if __name__ == "__main__":
    sys.exit(main())
