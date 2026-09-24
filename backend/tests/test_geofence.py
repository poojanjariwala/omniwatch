"""Pure-logic tests: geofence math, chain-of-custody hashing, randomness."""
from __future__ import annotations

from app.core.evidence_chain import (
    CHAIN_GENESIS, canonical_metadata, chain_hash, verify_chain_link,
)
from app.core.geofence import haversine_m, within_geofence
from app.core.randomization import (
    assignment_commitment, hybrid_priority, random_hex,
)


def test_haversine_scale():
    # ~111 km per degree of latitude.
    assert abs(haversine_m(0, 0, 1, 0) - 111_195) < 500
    assert haversine_m(28.6139, 77.2090, 28.6139, 77.2090) == 0.0


def test_within_geofence_reference():
    centre = (28.6139, 77.2090)
    inside, dist_near = within_geofence(centre[0] + 0.0002, centre[1], *centre, radius_m=50)
    outside, dist_far = within_geofence(centre[0] + 0.01, centre[1], *centre, radius_m=50)
    assert inside and dist_near <= 50
    assert not outside and dist_far > 50
    assert dist_far > 1000  # ~1.1 km


def test_evidence_chain_linking():
    meta_a = {"kind": "photo", "inspection_id": 1, "captured_at": "2026-01-01T10:00:00Z",
              "lat": 28.61, "lng": 77.2, "source": "live_camera"}
    h1 = chain_hash(CHAIN_GENESIS, "a" * 64, meta_a)
    meta_b = {**meta_a, "captured_at": "2026-01-01T10:05:00Z"}
    h2 = chain_hash(h1, "b" * 64, meta_b)
    assert h1 != h2 and h2 != CHAIN_GENESIS
    assert verify_chain_link(CHAIN_GENESIS, "a" * 64, meta_a, h1)
    assert not verify_chain_link(CHAIN_GENESIS, "a" * 64, {**meta_a, "lat": 0.0}, h1)
    # Canonical metadata ignores unknown keys (extras like hashes never leak in).
    assert canonical_metadata({"captured_at": "2026-01-01T10:00:00Z", "kind": "photo",
                               "secret": "x"}) == canonical_metadata(
        {"kind": "photo", "captured_at": "2026-01-01T10:00:00Z"})


def test_random_primitives():
    a, b = random_hex(16), random_hex(16)
    assert len(a) == 32 and a != b
    code, ts = "OWI-X-1", "2026-01-01T00:00:00+00:00"
    c = assignment_commitment(random_hex(16), code, ts)
    assert len(c) == 64
    # Deterministic on same inputs:
    assert assignment_commitment("n", code, ts) == assignment_commitment("n", code, ts)
    scores = [hybrid_priority(0.9) for _ in range(200)]
    assert all(0 <= s <= 1 for s in scores)
    assert len(set(round(s, 3) for s in scores)) > 10  # randomness preserved
