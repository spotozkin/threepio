"""Correlation between mic and speaker PCM for echo detection (barge-in gating)."""

from __future__ import annotations

from typing import Tuple

import numpy as np

_EPS = 1e-12
_TINY_NORM = 1e-9  # below this, segment is treated as silent (return NA)


def compute_best_abs_corr(
    mic: np.ndarray,
    spk: np.ndarray,
    sr: int,
    sweep_ms: int,
    step_ms: int,
) -> Tuple[float | None, int | None, str | None]:
    """
    Compute best absolute correlation between mic and speaker over a lag sweep.
    mic: last N samples (length N).
    spk: last (N + 2*sweep) samples so we can index y = spk[sweep+lag : sweep+lag+N] for lag in [-sweep, +sweep].
    Returns (corr, best_lag_ms, na_reason). na_reason is non-None only when returning (None, None, reason).
    """
    mic = np.asarray(mic, dtype=np.float64).flatten()
    spk = np.asarray(spk, dtype=np.float64).flatten()
    N = mic.size
    sweep_samp = int(sweep_ms * sr / 1000)
    step_samp = max(1, int(step_ms * sr / 1000))
    need_spk = N + 2 * sweep_samp

    if N < 10:
        return (None, None, "insufficient_samples")
    if spk.size < need_spk:
        return (None, None, "insufficient_samples")

    x = mic - np.mean(mic)
    best_corr = -1.0
    best_lag_ms: int | None = None
    had_valid_lag = False
    had_lag_in_bounds = False

    for lag_samp in range(-sweep_samp, sweep_samp + 1, step_samp):
        idx = sweep_samp + lag_samp
        if idx < 0 or idx + N > spk.size:
            continue
        y = spk[idx : idx + N].copy()
        if y.size != N:
            continue
        had_lag_in_bounds = True
        y = y - np.mean(y)
        nx = np.sqrt(np.dot(x, x) + _EPS)
        ny = np.sqrt(np.dot(y, y) + _EPS)
        if nx < _TINY_NORM or ny < _TINY_NORM:
            continue
        had_valid_lag = True
        c = abs(np.dot(x, y) / (nx * ny + _EPS))
        if c > best_corr:
            best_corr = c
            best_lag_ms = int(lag_samp * 1000 / sr)

    if not had_valid_lag:
        na_reason = "tiny_norm" if had_lag_in_bounds else "no_valid_lag"
        return (None, None, na_reason)
    if best_lag_ms is None:
        return (None, None, "no_valid_lag")
    return (float(best_corr), best_lag_ms, None)
