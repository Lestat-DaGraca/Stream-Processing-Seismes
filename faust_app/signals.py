from datetime import datetime, timedelta
from collections import deque
import math
from datetime import timezone

# Fenêtre de 10 minutes changé en 15 pour CSV 
WINDOW_DURATION = timedelta(minutes=15) 
MIN_EVENTS_FOR_ALERT = 5 # Nombre minimum d'événements pour évaluer le score

# État par région
foreshock_state = {}
def init_region_state():
    return {
        "events": deque(),           # timestamps des événements récents
        "last_event_time": None,
        "avg_inter_event": None,     # EMA du temps entre séismes (en secondes)
        "baseline_rate": None,       # événements / 10 min (long terme)
        "score": 0.0,
        "last_update": None
    }

def normalize_utc(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def update_foreshock_metric(region, event_time):
    now = normalize_utc(event_time)

    if region not in foreshock_state:
        foreshock_state[region] = init_region_state()

    state = foreshock_state[region]

    # Nettoyage de la fenêtre
    state["events"].append(now)
    while state["events"] and now - state["events"][0] > WINDOW_DURATION:
        state["events"].popleft()

    event_count = len(state["events"])

    #Temps entre événements (EMA simple)
    if state["last_event_time"] is not None:
        delta = (now - state["last_event_time"]).total_seconds()
        if state["avg_inter_event"] is None:
            state["avg_inter_event"] = delta
        else:
            alpha = 0.3
            state["avg_inter_event"] = (
                alpha * delta + (1 - alpha) * state["avg_inter_event"]
            )

    state["last_event_time"] = now

    # Baseline simple (apprentissage progressif)
    if event_count >= MIN_EVENTS_FOR_ALERT:
        if state["baseline_rate"] is None:
            state["baseline_rate"] = event_count
        else:
            beta = 0.05
            state["baseline_rate"] = (
                beta * event_count + (1 - beta) * state["baseline_rate"]
            )

    # Garde-fou : pas assez d'événements = pas de signal d'alerte
    if event_count < MIN_EVENTS_FOR_ALERT:
        score = 0.0
    else:
        # Score normalisé
        if state["baseline_rate"] > 0:
            activity_ratio = event_count / state["baseline_rate"]
            score = min(activity_ratio / 3.0, 1.0)
        else:
            score = 0.0

    state["score"] = round(score, 2)
    state["last_update"] = now

    return state


# État pour les magnitudes ascendantes
magnitude_trend_state = {}
def init_magnitude_trend_state():
    return {
        "magnitudes": deque(maxlen=6),  # N derniers séismes
        "slope": 0.0,
        "score": 0.0,
        "last_update": None
    }


def update_magnitude_trend(region, magnitude, event_time):
    now = normalize_utc(event_time)
    if region not in magnitude_trend_state:
        magnitude_trend_state[region] = init_magnitude_trend_state()

    state = magnitude_trend_state[region]
    mags = state["magnitudes"]

    mags.append(magnitude)
    # Pas assez de points → pas de signal
    if len(mags) < 4:
        state["score"] = 0.0
        state["last_update"] = now
        return state

    # Calcul de pente simple
    # (différence moyenne entre valeurs successives)
    diffs = [mags[i+1] - mags[i] for i in range(len(mags)-1)]
    avg_slope = sum(diffs) / len(diffs)

    state["slope"] = round(avg_slope, 3)

    # Normalisation du score
    if avg_slope <= 0:
        score = 0.0
    else:
        # pente ≥ 0.3 ≈ montée rapide → score max
        score = min(avg_slope / 0.3, 1.0)

    state["score"] = round(score, 2)
    state["last_update"] = now

    return state

energy_state = {}

def init_energy_state():
    return {
        "events": deque(),          # (timestamp, energy)
        "cumulative_energy": 0.0,   # énergie sur la fenêtre
        "baseline_energy": None,    # énergie moyenne long terme
        "score": 0.0,
        "last_update": None
    }
# Formule de Gutenberg-Richter conversion magnitude -> énergie (en joules)
def magnitude_to_energy(magnitude):
    return 10 ** (1.5 * magnitude + 4.8)

def update_energy_metric(region, magnitude, event_time):
    now = normalize_utc(event_time)

    if region not in energy_state:
        energy_state[region] = init_energy_state()

    state = energy_state[region]

    energy = magnitude_to_energy(magnitude)
    state["events"].append((now, energy))
    state["cumulative_energy"] += energy

    # Nettoyage fenêtre
    while state["events"] and now - state["events"][0][0] > WINDOW_DURATION:
        _, old_energy = state["events"].popleft()
        state["cumulative_energy"] -= old_energy

    # Baseline (EMA lente)
    if state["baseline_energy"] is None:
        state["baseline_energy"] = state["cumulative_energy"]
    else:
        beta = 0.10
        state["baseline_energy"] = (
            beta * state["cumulative_energy"]
            + (1 - beta) * state["baseline_energy"]
        )

    # Score
    if state["baseline_energy"] > 0:
        ratio = state["cumulative_energy"] / state["baseline_energy"]
        score = min(ratio / 4.0, 1.0)
    else:
        score = 0.0

    state["score"] = round(score, 2)
    state["last_update"] = now

    return state


# ===== SPATIAL CLUSTER - GRILLE SIMPLE =====
GRID_SIZE = 0.1  # degré latitude/longitude ≈ 10 km
CLUSTER_WINDOW = timedelta(minutes=30)
MIN_CLUSTER_EVENTS = 4

spatial_cluster_state = {}

def init_cluster_state():
    return {
        "events": deque(),       # timestamps récents
        "baseline": None,        # densité moyenne
        "score": 0.0,
        "last_update": None
    }

def get_grid_cell(latitude, longitude):
    """Retourne la clé de la cellule de grille pour lat/lon"""
    lat_cell = round(latitude / GRID_SIZE) * GRID_SIZE
    lon_cell = round(longitude / GRID_SIZE) * GRID_SIZE
    return f"{lat_cell:.2f}:{lon_cell:.2f}"

def update_spatial_cluster(region, latitude, longitude, event_time):
    now = normalize_utc(event_time)
    grid_key = get_grid_cell(latitude, longitude)
    cluster_key = f"{region}:{grid_key}"
    

    if cluster_key not in spatial_cluster_state:
        spatial_cluster_state[cluster_key] = init_cluster_state()

    state = spatial_cluster_state[cluster_key]

    # Ajout de l'événement
    state["events"].append(now)

    # Nettoyage fenêtre temporelle
    while state["events"] and now - state["events"][0] > CLUSTER_WINDOW:
        state["events"].popleft()

    event_count = len(state["events"])

    # Baseline adaptative
    if event_count >= MIN_CLUSTER_EVENTS:
        if state["baseline"] is None:
            state["baseline"] = event_count
        else:
            beta = 0.05
            state["baseline"] = (
                beta * event_count + (1 - beta) * state["baseline"]
            )

    # Score
    if event_count < MIN_CLUSTER_EVENTS:
        score = 0.0
    elif state["baseline"] is None or state["baseline"] == 0:
        # Pas encore de baseline : score linéaire conservateur
        score = min(event_count / (MIN_CLUSTER_EVENTS * 3.0), 0.7)
    else:
        # Score relatif : combien de fois au-dessus de la normale ?
        ratio = event_count / state["baseline"]
        # ratio=1 → score~0.33, ratio=2 → score~0.67, ratio=3+ → score=1.0
        score = min(ratio / 3.0, 1.0)

    state["score"] = round(score, 2)
    state["last_update"] = now

    return {
        "region": region,
        "grid_cell": grid_key,
        "event_count": event_count,
        "score": state["score"]
    }

""" Version avec geohash
import geohash2
# ===== SPATIAL CLUSTER (GEOHASH) =====
GEOHASH_PRECISION = 5           # ≈ 5–10 km
CLUSTER_WINDOW = timedelta(minutes=30)
MIN_CLUSTER_EVENTS = 4
spatial_cluster_state = {}

def init_cluster_state():
    return {
        "events": deque(),       # timestamps récents
        "baseline": None,        # densité moyenne
        "score": 0.0,
        "last_update": None
    }
def update_spatial_cluster(region, latitude, longitude, event_time):
    geohash_key = geohash2.encode(latitude, longitude, GEOHASH_PRECISION)
    cluster_key = f"{region}:{geohash_key}"

    if cluster_key not in spatial_cluster_state:
        spatial_cluster_state[cluster_key] = init_cluster_state()

    state = spatial_cluster_state[cluster_key]

    # Ajout de l'événement
    state["events"].append(event_time)

    # Nettoyage fenêtre temporelle
    while state["events"] and event_time - state["events"][0] > CLUSTER_WINDOW:
        state["events"].popleft()

    event_count = len(state["events"])

    # Baseline adaptative
    if event_count >= MIN_CLUSTER_EVENTS:
        if state["baseline"] is None:
            state["baseline"] = event_count
        else:
            beta = 0.05
            state["baseline"] = (
                beta * event_count + (1 - beta) * state["baseline"]
            )

    # Score
    if event_count < MIN_CLUSTER_EVENTS or not state["baseline"]:
        score = 0.0
    else:
        ratio = event_count / state["baseline"]
        score = min(ratio / 3.0, 1.0)

    state["score"] = round(score, 2)
    state["last_update"] = event_time

    return {
        "region": region,
        "geohash": geohash_key,
        "event_count": event_count,
        "score": state["score"]
    }
    """

# ===== AFTERSHOCKS ANORMAUX =====
MAINSHOCK_THRESHOLD = 4.5  # magnitude déclencheur
AFTERSHOCK_WINDOW = timedelta(hours=6)
MIN_AFTERSHOCKS = 5
aftershock_state = {}
def init_aftershock_state():
    return {
        "mainshock_time": None,
        "mainshock_magnitude": None,
        "aftershocks": deque(),     # (timestamp, magnitude)
        "baseline_count": None,
        "score": 0.0,
        "last_update": None
    }
def update_aftershock_metric(region, magnitude, event_time):
    event_time = normalize_utc(event_time)
    if region not in aftershock_state:
        aftershock_state[region] = init_aftershock_state()

    state = aftershock_state[region]

    # Détection d’un mainshock
    if magnitude >= MAINSHOCK_THRESHOLD:
        state["mainshock_time"] = event_time
        state["mainshock_magnitude"] = magnitude
        state["aftershocks"].clear()
        state["baseline_count"] = None
        state["score"] = 0.0
        state["last_update"] = event_time
        return state

    # Pas de mainshock = rien à analyser
    if not state["mainshock_time"]:
        return state

    # Fenêtre aftershock expirée
    if event_time - state["mainshock_time"] > AFTERSHOCK_WINDOW:
        return state

    # Enregistrement aftershock
    state["aftershocks"].append((event_time, magnitude))

    # Nettoyage sécurité (au cas où)
    while state["aftershocks"] and (
        event_time - state["aftershocks"][0][0] > AFTERSHOCK_WINDOW
    ):
        state["aftershocks"].popleft()

    count = len(state["aftershocks"])

    # Baseline simple
    if count >= MIN_AFTERSHOCKS:
        if state["baseline_count"] is None:
            state["baseline_count"] = count
        else:
            beta = 0.05
            state["baseline_count"] = (
                beta * count + (1 - beta) * state["baseline_count"]
            )

    # Score
    if count < MIN_AFTERSHOCKS or not state["baseline_count"]:
        score = 0.0
    else:
        ratio = count / state["baseline_count"]
        score = min(ratio / 3.0, 1.0)

    state["score"] = round(score, 2)
    state["last_update"] = event_time

    return state

# ===== ASYMMETRY METRIC (ACCÉLÉRATION TEMPORELLE) =====

ASY_WINDOW = timedelta(minutes=20)
MIN_ASY_EVENTS = 6

asymmetry_state = {}

def init_asymmetry_state():
    return {
        "events": deque(),     # timestamps
        "ratio": 0.0,
        "score": 0.0,
        "last_update": None
    }

def update_asymmetry_metric(cluster_id, event_time):
    now = normalize_utc(event_time)
    if cluster_id not in asymmetry_state:
        asymmetry_state[cluster_id] = init_asymmetry_state()

    state = asymmetry_state[cluster_id]

    state["events"].append(now)

    while state["events"] and now - state["events"][0] > ASY_WINDOW:
        state["events"].popleft()

    if len(state["events"]) < MIN_ASY_EVENTS:
        state["score"] = 0.0
        state["last_update"] = now
        return state

    mid_time = now - ASY_WINDOW / 2

    old_events = sum(1 for t in state["events"] if t < mid_time)
    recent_events = sum(1 for t in state["events"] if t >= mid_time)

    ratio = float(recent_events) if old_events == 0 else recent_events / old_events
    score = min(ratio / 2.0, 1.0)

    state["ratio"] = round(ratio, 2)
    state["score"] = round(score, 2)
    state["last_update"] = now

    return state


# ===== SPATIAL MIGRATION (avec cluster) =====

MIGRATION_WINDOW = timedelta(minutes=45)
MIN_MIGRATION_EVENTS = 5
MAX_VALID_DISTANCE_KM = 80   # au-delà = faux signal

spatial_migration_state = {}

def init_migration_state():
    return {
        "events": deque(),   # (timestamp, lat, lon)
        "score": 0.0,
        "distance_km": 0.0,
        "last_update": None
    }

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371  # Rayon Terre (km)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2)**2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def update_spatial_migration(cluster_key, latitude, longitude, event_time):
    event_time = normalize_utc(event_time)
    if cluster_key not in spatial_migration_state:
        spatial_migration_state[cluster_key] = init_migration_state()

    state = spatial_migration_state[cluster_key]

    # Ajout événement
    state["events"].append((event_time, latitude, longitude))

    # Nettoyage fenêtre
    while state["events"] and event_time - state["events"][0][0] > MIGRATION_WINDOW:
        state["events"].popleft()

    if len(state["events"]) < MIN_MIGRATION_EVENTS:
        state["score"] = 0.0
        state["last_update"] = event_time
        return state

    # Séparation ancien / récent
    events_list = list(state["events"])

    mid = len(events_list) // 2
    early = events_list[:mid]
    recent = events_list[mid:]

    def barycenter(points):
        lat = sum(p[1] for p in points) / len(points)
        lon = sum(p[2] for p in points) / len(points)
        return lat, lon

    lat1, lon1 = barycenter(early)
    lat2, lon2 = barycenter(recent)

    distance = haversine_km(lat1, lon1, lat2, lon2)
    state["distance_km"] = round(distance, 1)

    # Garde-fou distance irréaliste
    if distance > MAX_VALID_DISTANCE_KM:
        state["score"] = 0.0
    else:
        # 30 km ≈ migration forte
        score = min(distance / 30.0, 1.0)
        state["score"] = round(score, 2)

    state["last_update"] = event_time
    return state


FUSION_WEIGHTS = {
    "foreshock": 0.25,
    "trend": 0.15,
    "energy": 0.20,
    "asy": 0.15,
    "cluster": 0.10,
    "migration": 0.05
}
# ===== MULTI SIGNAL FUSION =====

def fuse_signals(metrics):
    """
    metrics = {
        "foreshock": score,
        "trend": score,
        "energy": score,
        "asy": score,
        "cluster": score,
        "migration": score
    }
    """

    # Règle 1 : pas d'alerte sans activité réelle
    if metrics.get("cluster", 0) < 0.2:
        return {
            "global_score": 0.0,
            "level": "NONE",
            "reason": "no_spatial_activity"
        }

    # Score pondéré
    weighted_score = 0.0
    for key, weight in FUSION_WEIGHTS.items():
        weighted_score += metrics.get(key, 0.0) * weight

    weighted_score = round(weighted_score, 2)

    # Règle 2 : au moins 2 signaux forts
    
    strong_signals = sum(1 for v in metrics.values() if v >= 0.7)
    if strong_signals < 2:
        return {
            "global_score": weighted_score,
            "level": "LOW",
            "reason": "insufficient_convergence"
        }

    # Niveaux d’alerte
    if weighted_score >= 0.75:
        level = "ALERT"
    elif weighted_score >= 0.55:
        level = "VIGILANCE"
    else:
        level = "LOW"

    return {
        "global_score": weighted_score,
        "level": level,
        "strong_signals": strong_signals
    }
