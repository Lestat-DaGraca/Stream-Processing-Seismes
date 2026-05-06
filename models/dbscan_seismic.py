from collections import deque
from datetime import timedelta, datetime, timezone
import numpy as np
from sklearn.cluster import DBSCAN
from incdbscan import IncrementalDBSCAN

from tables import clusters_snapshot_dict, seismic_points_flat, active_regions_list

incdbscan_models = {}
WINDOW_SIZE = timedelta(hours=1)  # taille de la fenêtre glissante


def cluster_earthquakes(points, eps_km=50, min_samples=5):
    """Regroupe les événements sismiques en clusters à l'aide de DBSCAN """

    res = []
    if len(points) >= min_samples:
        coords = np.array([
            [point["lat"], point["lon"]] for point in points
        ])

        db = DBSCAN(
            eps=eps_km / 111.0,
            min_samples=min_samples,
            metric="euclidean",
        ).fit(coords)

        clusters = {}
        for label, point in zip(db.labels_, points):
            if label == -1:
                continue
            clusters.setdefault(label, []).append(point)

        res = list(clusters.values())
    return res

def _to_datetime(t):
    """
    Normalise en datetime naive UTC.
    """
    if isinstance(t, str):
        dt = datetime.fromisoformat(t)
        return dt.replace(tzinfo=None)
    if isinstance(t, datetime):
        return t.replace(tzinfo=None)
    return t


def update_clusters_incremental(region, new_point, quake_time, eps_km=50, min_samples=5):
    """
    Ajoute le point au modèle et supprime les points expirés selon la fenêtre.
    """
    quake_time = _to_datetime(quake_time)
    cutoff = datetime.utcnow() - WINDOW_SIZE

    #Récupère la deque
    flat_points = seismic_points_flat.get(region)
    if not isinstance(flat_points, deque):
        flat_points = deque(flat_points) if flat_points else deque()

    #Initialise le modèle si nécessaire
    if region not in incdbscan_models:
        model = IncrementalDBSCAN(eps=eps_km / 111.0, min_pts=min_samples)
        for p in flat_points:
            if _to_datetime(p["time"]) >= cutoff:
                model.insert(np.array([[p["lat"], p["lon"]]]))
        incdbscan_models[region] = model

    model = incdbscan_models[region]

    #Purge des points expirés
    expired_count = 0
    while flat_points:
        oldest_time = _to_datetime(flat_points[0]["time"])
        print(f"oldest_time : {oldest_time}")
        if oldest_time < cutoff:
            old_point = flat_points.popleft()
            try:
                model.delete(np.array([[old_point["lat"], old_point["lon"]]]))
                expired_count += 1
            except Exception as e:
                print(f"[WARN] Suppression échouée : {e}")
        else:
            break

    #Normalise et insère le nouveau point
    new_point = {**new_point, "time": quake_time}
    flat_points.append(new_point)
    seismic_points_flat[region] = flat_points
    model.insert(np.array([[new_point["lat"], new_point["lon"]]]))


def init_incdbscan_for_region(region, points, eps_km=50, min_samples=5):
    """
    Initialise un modèle IncrementalDBSCAN pour une région donnée.
    """
    model = IncrementalDBSCAN(eps=eps_km / 111.0, min_pts=min_samples)

    for p in points:
        model.insert(np.array([[p["lat"], p["lon"]]]))

    incdbscan_models[region] = model
    return model

def get_clusters_from_model(region):
    model = incdbscan_models.get(region)
    points = seismic_points_flat.get(region, [])

    if not model or len(points) == 0:
        return []

    coords = np.array([[p["lat"], p["lon"]] for p in points])
    labels = model.get_cluster_labels(coords)

    clusters_dict = {}
    for label, point in zip(labels, points):
        if label == -1 or np.isnan(label):
            continue
        clusters_dict.setdefault(int(label), []).append(point)
    
    print(f"[INFO] {region} → {len(clusters_dict)} clusters extraits du modèle incrémental")

    return [
        {
            "region": region,
            "size": len(cluster),
            "avg_magnitude": round(
                sum(p["mag"] for p in cluster) / len(cluster), 2
            ),
            "points": cluster,
        }
        for cluster in clusters_dict.values()
    ]

def remove_expired_points(region, current_window):
    """
    Supprime du modèle les points qui ne sont plus dans la fenêtre glissante
    """
    flat_points = seismic_points_flat.get(region, [])

    #on garde uniquement les points présents dans la fenêtre
    window_set = {(p["lat"], p["lon"], p["time"]) for p in current_window}

    new_flat = []
    removed_points = []

    for p in flat_points:
        key = (p["lat"], p["lon"], p["time"])
        if key in window_set:
            new_flat.append(p)
        else:
            removed_points.append(p)

    seismic_points_flat[region] = new_flat

    #suppression dans le modèle incrémental
    if region in incdbscan_models:
        model = incdbscan_models[region]

        for p in removed_points:
            try:
                model.delete(np.array([[p["lat"], p["lon"]]]))
            except Exception:
                pass