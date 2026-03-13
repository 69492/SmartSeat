"""
ml_model.py
-----------
ML-based ranking module for the Dynamic Train Seat Allocation System.

Purpose
=======
When multiple valid berths are available after the CSP check, this module
ranks them using a trained classifier and returns the highest-scoring one.

ML is used ONLY for ranking — feasibility is determined solely by the CSP
engine in allocation_engine.py.

Model
=====
A Decision Tree classifier (or Logistic Regression) is trained on
synthetically generated preference data each time the application starts.
The model is intentionally lightweight so it adds no deployment overhead.

Features used for ranking
==========================
1. journey_distance  — number of stations covered (higher = preferred)
2. berth_type_enc    — encoded berth type (LB=0, MB=1, UB=2, SL=3, SU=4)
3. is_full_vacant    — 1 if FULL_VACANT, 0 if PARTIAL
4. coach_no          — numeric part of coach name (S1→1, S2→2, …)
5. berth_position    — berth_no within coach (lower number slightly preferred)
"""

from __future__ import annotations

import logging
import random
from typing import Any

import numpy as np
from sklearn.tree import DecisionTreeClassifier

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

BERTH_TYPE_MAP: dict[str, int] = {
    "LB": 0,   # Lower Berth  — most preferred
    "MB": 1,
    "UB": 2,
    "SL": 3,
    "SU": 4,   # Side Upper   — least preferred
}


def _encode_candidate(candidate: dict[str, Any]) -> list[float]:
    """Convert a candidate dict into a feature vector."""
    berth_type_enc  = BERTH_TYPE_MAP.get(candidate.get("berth_type", "UB"), 2)
    is_full_vacant  = 1 if candidate.get("allocation_type") == "FULL_VACANT" else 0
    coach_str       = candidate.get("coach", "S1")
    coach_no        = int(coach_str[1:]) if coach_str[1:].isdigit() else 1
    berth_pos       = candidate.get("berth_no", 1)
    journey_dist    = candidate.get("journey_distance", 1)

    return [journey_dist, berth_type_enc, is_full_vacant, coach_no, berth_pos]


# ---------------------------------------------------------------------------
# Synthetic training data generator
# ---------------------------------------------------------------------------

def _generate_training_data(
    n_samples: int = config.ML_TRAINING_SAMPLES,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build a synthetic labelled dataset that encodes commonsense seat
    preferences for Indian Railways sleeper class.

    Label = 1  →  "good" seat (preferred)
    Label = 0  →  "poor" seat
    """
    rng = random.Random(0)
    X: list[list[float]] = []
    y: list[int] = []

    for _ in range(n_samples):
        journey_dist    = rng.randint(1, 9)
        berth_type_enc  = rng.randint(0, 4)          # 0=LB … 4=SU
        is_full_vacant  = rng.randint(0, 1)
        coach_no        = rng.randint(1, 6)
        berth_pos       = rng.randint(1, 72)

        # Heuristic preference scoring
        score = 0.0
        score += journey_dist * 0.5                  # longer journeys prefer definite seats
        score += (4 - berth_type_enc) * 1.5          # LB(0) → highest; SU(4) → lowest
        score += is_full_vacant * 2.0                # definite vacancy preferred
        score -= coach_no * 0.3                      # lower coach number slightly preferred
        score -= (berth_pos / 72) * 0.5              # lower berth numbers slightly preferred

        label = 1 if score >= rng.uniform(2.5, 5.0) else 0
        X.append([journey_dist, berth_type_enc, is_full_vacant, coach_no, berth_pos])
        y.append(label)

    return np.array(X, dtype=float), np.array(y, dtype=int)


# ---------------------------------------------------------------------------
# Model wrapper
# ---------------------------------------------------------------------------

class BerthRanker:
    """
    Thin wrapper around a Decision Tree that ranks candidate berths.

    Usage
    -----
    >>> ranker = BerthRanker()
    >>> ranker.train()
    >>> best = ranker.rank(candidates)
    """

    def __init__(self) -> None:
        self._model: DecisionTreeClassifier | None = None

    def train(self) -> None:
        """Train the model on synthetic preference data."""
        X, y = _generate_training_data()
        self._model = DecisionTreeClassifier(
            max_depth=config.ML_MAX_DEPTH,
            random_state=config.ML_RANDOM_STATE,
        )
        self._model.fit(X, y)

    def rank(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Return the best candidate from *candidates*.

        If the model is not trained, or no candidate scores positively, the
        first candidate (CSP order) is returned as a safe fallback.
        """
        if not candidates:
            raise ValueError("Candidate list is empty.")

        if self._model is None:
            return candidates[0]

        feature_matrix = np.array(
            [_encode_candidate(c) for c in candidates], dtype=float
        )
        # Probability of class-1 ("good seat")
        proba = self._model.predict_proba(feature_matrix)
        class_1_idx = list(self._model.classes_).index(1) if 1 in self._model.classes_ else 0
        scores = proba[:, class_1_idx]

        best_idx = int(np.argmax(scores))
        return candidates[best_idx]


# ---------------------------------------------------------------------------
# Module-level singleton — initialised once at import time
# ---------------------------------------------------------------------------

_ranker = BerthRanker()
_ranker.train()


def get_best_berth(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Public helper: return the ML-ranked best berth from *candidates*.

    Falls back to candidates[0] if the model is unavailable.
    """
    return _ranker.rank(candidates)
