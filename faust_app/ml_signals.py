from collections import deque
import numpy as np
from sklearn.ensemble import IsolationForest

# Configuration
ML_BASELINE_SIZE = 100    # Samples normaux pour figer la baseline
ML_MIN_TRAIN = 50        # Minimum avant premier entraînement
ML_CONTAMINATION = 0.05

_baseline_buffer = []    # Baseline normale figée après ML_BASELINE_SIZE samples
_baseline_frozen = False # True une fois la baseline figée
_model = IsolationForest(
    n_estimators=100,
    contamination=ML_CONTAMINATION,
    random_state=42
)
_ready = False

# Score min/max observés sur la baseline pour normalisation
_baseline_score_min = None
_baseline_score_max = None

def update_ml_anomaly_score(feature_vector):
    global _ready, _baseline_frozen, _baseline_score_min, _baseline_score_max

    fv = [float(x) for x in feature_vector]

    # Phase 1 : accumulation baseline (pas de scoring)
    if not _baseline_frozen:
        _baseline_buffer.append(fv)

        if len(_baseline_buffer) < ML_MIN_TRAIN:
            return {"score": 0.0, "ready": False}

        # On a assez de données : entraîner sur la baseline normale
        X = np.array(_baseline_buffer)
        _model.fit(X)

        # Calibrer min/max sur la baseline elle-même
        raw_scores = -_model.score_samples(X)
        _baseline_score_min = float(np.percentile(raw_scores, 10))
        _baseline_score_max = float(np.percentile(raw_scores, 90))

        if len(_baseline_buffer) >= ML_BASELINE_SIZE:
            _baseline_frozen = True  
            _ready = True

        return {"score": 0.0, "ready": False}

    # Phase 2 : scoring pur, modèle figé
    raw = float(-_model.score_samples([fv])[0])

    # Normalisation relative à la baseline
    # raw == baseline_min -> score ~0.0 (normal)
    # raw >> baseline_max -> score -> 1.0 (anomalie franche)
    spread = _baseline_score_max - _baseline_score_min
    if spread < 1e-6:
        spread = 0.1

    score = (raw - _baseline_score_min) / (spread * 1.0)
    score = round(min(max(score, 0.0), 1.0), 2)

    return {
        "score": score,
        "ready": True,
        "raw": round(raw, 3)
    }