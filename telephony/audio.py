"""
Telephony audio normalization (transport boundary only).

Converts inbound telephony audio into the project's canonical representation
— mono 16 kHz int16 PCM, exactly what gateway/live_gateway.py buffers — using
the same resampling primitive (scipy.signal.resample_poly) as the existing
preprocessor. The VAD/pipeline are never modified here.

Supported telephony payloads (honestly bounded):
- RTP payload type 0 .......... PCMU (G.711 µ-law, 8 kHz)
- RTP payload type 8 .......... PCMA (G.711 A-law, 8 kHz)
- RTP dynamic L16 (16-bit linear, negotiated rate) via explicit opt-in
- Provider media streams ...... base64 G.711 µ-law frames (8 kHz)

Anything else raises UnsupportedCodecError — missing or undecodable audio is
counted as dropped, never replaced with generated samples.
"""

from __future__ import annotations

import logging
import math
import struct
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000

PT_PCMU = 0
PT_PCMA = 8


class RtpError(ValueError):
    """Malformed RTP packet (too short, bad version, truncated)."""


class UnsupportedCodecError(ValueError):
    """Payload type / encoding the adapter cannot normalize."""


# ── G.711 companding (ITU-T G.711, vectorized) ─────────────────────────────


def mulaw_to_pcm16(payload: bytes) -> np.ndarray:
    """Decode G.711 µ-law bytes to int16 PCM (8 kHz sample rate implied)."""
    if not payload:
        raise RtpError("Empty µ-law payload")
    u = np.frombuffer(payload, dtype=np.uint8).astype(np.int32)
    u = ~u & 0xFF
    sign = u & 0x80
    exponent = (u >> 4) & 0x07
    mantissa = u & 0x0F
    sample = ((mantissa << 3) + 0x84) << exponent
    sample = sample - 0x84
    sample = np.where(sign != 0, -sample, sample)
    return np.clip(sample, -32768, 32767).astype(np.int16)


def alaw_to_pcm16(payload: bytes) -> np.ndarray:
    """Decode G.711 A-law bytes to int16 PCM (8 kHz sample rate implied)."""
    if not payload:
        raise RtpError("Empty A-law payload")
    a = np.frombuffer(payload, dtype=np.uint8).astype(np.int32)
    a ^= 0x55
    sign = a & 0x80
    exponent = (a >> 4) & 0x07
    mantissa = a & 0x0F
    if_exponent_zero = (mantissa << 4) + 8
    if_exponent_nz = ((mantissa << 4) + 0x108) << (exponent - 1)
    sample = np.where(exponent == 0, if_exponent_zero, if_exponent_nz)
    sample = np.where(sign != 0, sample, -sample)
    return np.clip(sample, -32768, 32767).astype(np.int16)


def l16_to_pcm16(payload: bytes, big_endian: bool = True) -> np.ndarray:
    """Pass through 16-bit linear telephony payloads (host-endian int16 out)."""
    if not payload or len(payload) % 2 != 0:
        raise RtpError("Truncated L16 payload")
    fmt = ">i2" if big_endian else "<i2"
    return np.frombuffer(payload, dtype=fmt).astype(np.int16)


def resample_to_16k(mono_i16: np.ndarray, in_rate: int) -> np.ndarray:
    """Resample mono int16 audio to 16 kHz (passthrough when already 16 kHz)."""
    if mono_i16.size == 0:
        raise RtpError("Empty audio after decode")
    if in_rate == TARGET_SAMPLE_RATE:
        return mono_i16.astype(np.int16)
    if in_rate <= 0:
        raise RtpError(f"Invalid telephony sample rate: {in_rate}")
    import scipy.signal

    gcd = math.gcd(in_rate, TARGET_SAMPLE_RATE)
    up = TARGET_SAMPLE_RATE // gcd
    down = in_rate // gcd
    out = scipy.signal.resample_poly(mono_i16.astype(np.float64), up, down)
    return np.clip(out, -32768, 32767).astype(np.int16)


def normalize_telephony_payload(
    payload_type: int,
    payload: bytes,
    in_rate: int = 8000,
    l16_big_endian: bool = True,
) -> Tuple[np.ndarray, str]:
    """Decode + canonicalize one telephony payload unit.

    Returns (pcm16_mono_16k, codec_name). Raises UnsupportedCodecError for
    payload types outside the supported set, RtpError for empty/truncated
    payloads.
    """
    if payload_type == PT_PCMU:
        return resample_to_16k(mulaw_to_pcm16(payload), 8000), "PCMU"
    if payload_type == PT_PCMA:
        return resample_to_16k(alaw_to_pcm16(payload), 8000), "PCMA"
    if payload_type == 96 and in_rate in (8000, 16000):
        # Locally-negotiated dynamic L16 only — never assumed for providers.
        return resample_to_16k(l16_to_pcm16(payload, l16_big_endian), in_rate), "L16"
    raise UnsupportedCodecError(f"Unsupported telephony payload type {payload_type}")


# ── RTP parsing (RFC 3550, minimal honest subset) ──────────────────────────


@dataclass
class RtpPacket:
    payload_type: int
    sequence: int
    timestamp: int
    ssrc: int
    payload: bytes
    marker: bool = False


def parse_rtp(datagram: bytes) -> RtpPacket:
    """Parse one UDP datagram as RTP. Raises RtpError on any malformation."""
    if len(datagram) < 12:
        raise RtpError(f"Datagram too short for RTP ({len(datagram)} bytes)")
    b0, b1, seq, ts, ssrc = struct.unpack(">BBHII", datagram[:12])
    if (b0 >> 6) != 2:
        raise RtpError(f"Not an RTP packet (version {(b0 >> 6)})")
    csrc_count = b0 & 0x0F
    header_len = 12 + csrc_count * 4
    has_extension = bool(b0 & 0x10)
    has_padding = bool(b0 & 0x20)
    if has_extension:
        if len(datagram) < header_len + 4:
            raise RtpError("Truncated RTP header extension")
        ext_len_words = struct.unpack(">H", datagram[header_len + 2 : header_len + 4])[0]
        header_len += 4 + ext_len_words * 4
    if len(datagram) < header_len:
        raise RtpError("Truncated RTP header (CSRC)")
    payload = datagram[header_len:]
    if has_padding:
        if not payload:
            raise RtpError("Truncated RTP padding")
        pad = payload[-1]
        if pad > len(payload):
            raise RtpError("Invalid RTP padding length")
        payload = payload[: len(payload) - pad] if pad else payload
    if not payload:
        raise RtpError("RTP packet carries no media payload")
    return RtpPacket(
        payload_type=b1 & 0x7F,
        sequence=seq,
        timestamp=ts,
        ssrc=ssrc,
        payload=bytes(payload),
        marker=bool(b1 & 0x80),
    )


@dataclass
class RtpStreamTracker:
    """Per-stream (SSRC) continuity accounting: loss, jitter, discontinuities.

    Loss is counted from 16-bit sequence gaps (missing packets are counted,
    never concealed). Jitter follows RFC 3550 A.8 interarrival estimate in
    media-clock units, reported as max observed milliseconds.
    """

    clock_rate: int = 8000
    last_sequence: Optional[int] = None
    last_timestamp: Optional[int] = None
    last_arrival_q16: Optional[int] = None
    jitter_units: float = 0.0
    jitter_max_ms: float = 0.0
    packets_received: int = 0
    packets_lost: int = 0
    discontinuities: int = 0
    ssrc_changes: int = 0
    current_ssrc: Optional[int] = None

    def observe(self, pkt: RtpPacket, arrival_q16: Optional[int] = None) -> str:
        """Account for one packet. Returns 'ok' | 'duplicate' | 'late'."""
        import time as _time

        if self.current_ssrc is None:
            self.current_ssrc = pkt.ssrc
        elif pkt.ssrc != self.current_ssrc:
            self.ssrc_changes += 1
            self.discontinuities += 1
            self.current_ssrc = pkt.ssrc
            self.last_sequence = None
            self.last_timestamp = None

        if arrival_q16 is None:
            arrival_q16 = int(_time.monotonic() * 65536)

        outcome = "ok"
        if self.last_sequence is not None:
            gap = (pkt.sequence - self.last_sequence) % 65536
            if gap == 0:
                outcome = "duplicate"
            elif gap > 1:
                if gap < 1000:
                    self.packets_lost += gap - 1
                else:
                    # Sequence restart / huge jump: discontinuity, not loss.
                    self.discontinuities += 1
            if self.last_timestamp is not None and outcome == "ok":
                arrival_delta = arrival_q16 - (self.last_arrival_q16 or arrival_q16)
                arrival_media = arrival_delta * self.clock_rate / 65536.0
                ts_delta = (pkt.timestamp - self.last_timestamp) % 2**32
                if ts_delta > 2**31:
                    ts_delta -= 2**32
                d = abs(arrival_media - ts_delta)
                self.jitter_units += (d - self.jitter_units) / 16.0
                self.jitter_max_ms = max(
                    self.jitter_max_ms, self.jitter_units * 1000.0 / self.clock_rate
                )

        if outcome != "duplicate":
            self.last_sequence = pkt.sequence
            self.last_timestamp = pkt.timestamp
            self.last_arrival_q16 = arrival_q16
            self.packets_received += 1
        return outcome
