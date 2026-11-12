"""Z-score anomaly flagging for a single resampled series."""

from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_THRESHOLD = 3.0


def zscores(values) -> np.ndarray:
    """Population z-scores; all-NaN-safe and flat-series-safe (returns zeros)."""
    arr = np.asarray(list(values), dtype=float)
    scores = np.zeros(arr.shape, dtype=float)
    valid = ~np.isnan(arr)
    if valid.sum() < 3:
        return scores
    mean = float(arr[valid].mean())
    std = float(arr[valid].std(ddof=0))
    if not np.isfinite(std) or std == 0.0:
        return scores
    scores[valid] = (arr[valid] - mean) / std
    return scores


def flag_mask(values, threshold: float = DEFAULT_THRESHOLD) -> np.ndarray:
    """Boolean mask of points whose |z| is at or above `threshold`."""
    if threshold <= 0:
        raise ValueError("Threshold must be greater than zero.")
    return np.abs(zscores(values)) >= float(threshold)


def flag_frame(frame: pd.DataFrame, column: str = "value", threshold: float = DEFAULT_THRESHOLD) -> pd.DataFrame:
    """Return a copy of the frame with `z` and `is_anomaly` columns added."""
    result = frame.copy()
    result["z"] = zscores(result[column].to_numpy())
    result["is_anomaly"] = np.abs(result["z"].to_numpy()) >= float(threshold)
    return result


def summarise(frame: pd.DataFrame) -> dict:
    """Human summary of flagged points in an already-flagged frame."""
    if frame.empty or "is_anomaly" not in frame:
        return {"count": 0, "first": None, "peak_abs_z": 0.0}
    flagged = frame[frame["is_anomaly"]]
    peak = float(frame["z"].abs().max()) if "z" in frame else 0.0
    first = None
    if not flagged.empty and "ts" in flagged:
        first = str(flagged.iloc[0]["ts"])
    return {"count": int(len(flagged)), "first": first, "peak_abs_z": round(peak, 2)}
