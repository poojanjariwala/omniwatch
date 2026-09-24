"""Cryptographically auditable randomization primitives.

Every inspection assignment records a nonce + SHA-256 commitment so the draw
can be independently re-verified, preserving both auditability and the
unpredictability of blind assignment.
"""
from __future__ import annotations

import hashlib
import secrets


def random_hex(bytes_len: int = 16) -> str:
    """Cryptographically secure hex string (default 16 bytes => 32 hex chars)."""
    return secrets.token_hex(bytes_len)


def random_below(n: int) -> int:
    return secrets.randbelow(max(1, n))


def assignment_commitment(nonce: str, inspection_code: str, ts_iso: str) -> str:
    """Commitment over the draw inputs: SHA-256(nonce || code || timestamp)."""
    return hashlib.sha256(f"{nonce}||{inspection_code}||{ts_iso}".encode("utf-8")).hexdigest()


def hybrid_priority(risk_signal: float, risk_weight: float = 0.6) -> float:
    """Random + risk-priority hybrid in [0,1].

    A uniform draw keeps even low-risk projects eligible (unpredictability);
    the validated risk signal biases, but never guarantees, selection.
    """
    rand = secrets.SystemRandom().random()
    return min(1.0, risk_weight * risk_signal + (1.0 - risk_weight) * rand)
