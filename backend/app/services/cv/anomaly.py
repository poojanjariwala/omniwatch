"""Adaptive baselines and anomaly rules.

Anomaly = DETECT + PRIORITIZE only. Output is an explainable risk signal;
verification and decisions always belong to authorized officials.
"""
from __future__ import annotations

from dataclasses import dataclass, field

ALPHA = 0.15          # EWMA smoothing for the "normal" reference
SURGE_MULT = 1.8      # occupancy must exceed baseline * this to flag
SURGE_MIN_ABS = 14    # ... and be at least this many people (demo scale)
MIN_SAMPLES = 4       # warm-up samples before evaluation is meaningful
DUMP_THRESHOLD = 0.6  # change to a genuinely abnormal pattern

SURGE_BURST_WINDOW_S = 300   # 'tip-off' style: N arrivals within 5 minutes
SURGE_BURST_DELTA = 25       # arrivals above expected within the window


@dataclass
class AnomalyVerdict:
    flagged: bool
    kind: str | None = None  # activity_surge | tip_off
    severity: str = "info"
    risk: float = 0.0
    signals: list = field(default_factory=list)
    explanation: str = ""


def _severity_for(risk: float) -> str:
    if risk >= 0.7:
        return "critical"
    if risk >= 0.45:
        return "warning"
    return "info"


def evaluate_window(
    *,
    occupancy: int,
    items: int | None,
    ewma: float,
    ewma_items: float,
    sample_count: int,
    window_seconds: int,
) -> AnomalyVerdict:
    """Evaluate one observed window against the project baseline."""
    if sample_count < MIN_SAMPLES:
        return AnomalyVerdict(flagged=False, explanation="baseline warming up")

    base_occupancy = max(1.0, ewma)
    # Steady healthy activity: slight fluctuations around the baseline.
    if occupancy <= base_occupancy * SURGE_MULT:
        return AnomalyVerdict(flagged=False, explanation="within normal band")

    ratio = occupancy / base_occupancy
    risk = min(1.0, (ratio - 1.0) / (SURGE_MULT * 1.6))
    signals = [
        {"type": "cctv_occupancy", "observed": occupancy,
         "baseline_ewma": round(base_occupancy, 2), "ratio": round(ratio, 2),
         "window_seconds": window_seconds},
    ]
    if items is not None and ewma_items > 0:
        item_ratio = items / max(1.0, ewma_items)
        signals.append({"type": "cctv_items_handed", "observed": items,
                        "baseline_ewma": round(ewma_items, 2), "ratio": round(item_ratio, 2)})
    # A sustained band shift (> threshold) is a pattern change, not a spike.
    if ratio > DUMP_THRESHOLD + 1.0:
        kind, severity = "tip_off", "critical"
        explanation = (f"Occupancy {occupancy} is {ratio:.1f}x the project baseline "
                       f"({base_occupancy:.0f}) — possible staged crowd / tip-off.")
    else:
        kind, severity = "activity_surge", _severity_for(risk)
        explanation = (f"Sudden activity surge: {occupancy} people observed vs typical "
                       f"~{base_occupancy:.0f} ({ratio:.1f}x baseline).")
    return AnomalyVerdict(flagged=True, kind=kind, severity=severity, risk=risk,
                          signals=signals, explanation=explanation)


def updated_baseline(ewma: float, ewma_items: float, count: int,
                     occupancy: int, items: int | None) -> tuple[float, float, int]:
    """EWMA update that ignores extreme outliers (so one alarm can't warp the norm)."""
    base = max(1.0, ewma) if count else float(occupancy)
    if occupancy > base * SURGE_MULT:
        return ewma, ewma_items, count + 1
    new_ewma = ALPHA * occupancy + (1 - ALPHA) * (ewma or occupancy)
    new_items = ALPHA * (items or 0) + (1 - ALPHA) * (ewma_items or (items or 0)) if ewma_items or items else 0.0
    return round(new_ewma, 3), round(new_items, 3), count + 1
