"""Evidence integrity: per-artifact SHA-256 plus a linked chain-of-custody.

chain_hash = SHA-256( prev_chain_hash || artifact_sha256 || canonical_metadata )
so every artifact is bound to its predecessor and to who/what/when context.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

CHAIN_GENESIS = hashlib.sha256(b"OMNIWATCH-CHAIN-V1-GENESIS").hexdigest()
_META_KEYS = ("captured_at", "kind", "inspection_id", "case_id", "alert_id",
              "project_id", "source", "lat", "lng", "client_ref")


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_metadata(meta: dict | None) -> str:
    meta = meta or {}
    ordered = {k: meta.get(k) for k in _META_KEYS if k in meta}
    return json.dumps(ordered, sort_keys=True, separators=(",", ":"))


def chain_hash(prev_hash: str, artifact_sha256: str, meta: dict | None) -> str:
    payload = f"{prev_hash}||{artifact_sha256}||{canonical_metadata(meta)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_chain_link(
    prev_hash: str, artifact_sha256: str, meta: dict | None, expected: str
) -> bool:
    return chain_hash(prev_hash, artifact_sha256, meta) == expected
