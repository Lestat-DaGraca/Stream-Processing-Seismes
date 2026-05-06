from datetime import datetime
import hashlib
import heapq
from flask import json
from app import app, latest_quakes
from faust_app.signals import fuse_signals, update_aftershock_metric, update_asymmetry_metric, update_energy_metric, update_foreshock_metric, update_magnitude_trend, update_spatial_cluster, update_spatial_migration
from models.dbscan_seismic import cluster_earthquakes, get_clusters_from_model, update_clusters_incremental
from topics import earthquake_topic, usgs_by_region_topic
from tables import stats_table, windowed_stats, latest_trends, active_regions, seismic_points_flat, windowed_region_counts, clusters_snapshot_dict  , seismic_points
from partitioner.geo_partitioner import detect_geographical_zone
from signals import *
from ml_signals import update_ml_anomaly_score
from kmeans import update_signal

# Structures pour Top-K
top_k_by_region = {}
K_GLOBAL = 10
K_REGION = 10
active_regions_list = {"regions": []}

all_earthquakes = []

def update_top_k(heap, item, k):
    """
    Met à jour un heap pour maintenir les k plus grands éléments.
    item = (magnitude, quake_info)
    """
    magnitude, quake_info = item
    comparable_item = (magnitude, id(quake_info), quake_info)

    if len(heap) < k:
        heapq.heappush(heap, comparable_item)
    elif magnitude > heap[0][0]:
        heapq.heappushpop(heap, comparable_item)
    
    return heap

@app.agent(earthquake_topic)
async def process_quakes(quakes):
    """
    Traitement des séismes entrants
    """
    global top_k_global, all_earthquakes  

    async for quake in quakes:
        global_stats = stats_table['global']
        global_stats["sum"] += quake.magnitude
        global_stats["count"] += 1
        stats_table['global'] = dict(global_stats)

        avg_global = round(global_stats["sum"] / global_stats["count"], 2)

        region = detect_geographical_zone(quake.latitude, quake.longitude)
        windowed_region_counts[region] += 1

        snapshot = []
        for reg in ["Antarctica", "NorthAmerica", "SouthAmerica", "Europe", "Africa", "Asia", "Oceania", "Unknown"]:
            count_10min = windowed_region_counts[reg].current() if hasattr(windowed_region_counts[reg], 'current') else windowed_region_counts[reg].value()
            snapshot.append({
                "region": reg,
                "count": count_10min
            })

        latest_trends['snapshot'] = snapshot

        latest_quakes.append({
            "name": quake.place.split(",")[-1].strip(),
            "coords": (quake.latitude, quake.longitude),
            "magnitude": round(quake.magnitude, 2),
            "date": quake.time,
            "region": detect_geographical_zone(quake.latitude, quake.longitude)
        })

        if len(latest_quakes) > 4:
            latest_quakes.pop(0)

        quake_info = {
            "place": quake.place,
            "magnitude": round(quake.magnitude, 2),
            "latitude": quake.latitude,
            "longitude": quake.longitude,
            "time": quake.time if isinstance(quake.time, str) else quake.time.isoformat(),
            "region": detect_geographical_zone(quake.latitude, quake.longitude)
        }

        all_earthquakes.append(quake_info)
        if len(all_earthquakes) > 5000:
            all_earthquakes.pop(0)
        
        # signal pour cluster kmean
        update_signal.notify_new_earthquake()
        print(f" Signal envoyé : nouveau séisme {quake.place}")
        

@app.agent(usgs_by_region_topic)
async def process_quakes_by_region(stream):
    """
    Traitement des séismes par région
    """
    global top_k_by_region
    
    async for quake in stream:
        region_key = detect_geographical_zone(quake.latitude, quake.longitude)

        active_regions[region_key] = True
        if region_key not in active_regions_list["regions"]:
            active_regions_list["regions"].append(region_key)

        quake_time = quake.time
        if isinstance(quake_time, str):
            quake_time = datetime.fromisoformat(quake_time)

        window = windowed_stats[region_key].current()
        window["sum"] += quake.magnitude
        window["count"] += 1

        windowed_stats[region_key] = window

        window_avg = round(window["sum"] / window["count"], 2) if window["count"] > 0 else 0.0
        chart_data = []
        
        seismic_window = seismic_points[region_key].current()
        quake_time_dt = datetime.fromisoformat(quake.time) if isinstance(quake.time, str) else quake.time
        new_point = {
            "lat": quake.latitude,
            "lon": quake.longitude,
            "mag": quake.magnitude,
            "time": quake_time_dt
        }

        seismic_window.append(new_point)
        seismic_points[region_key] = seismic_window
        #seismic_points_flat[region_key] = list(seismic_window)
        ingest_time = datetime.utcnow()
        update_clusters_incremental(region_key, new_point, ingest_time)
        print(f"[INFO] {quake.place} (M{quake.magnitude}) traité | Point ajouté à la fenêtre de {region_key} | Total points={len(seismic_window)}")

        for region in windowed_stats.keys():
            stats = windowed_stats[region].value()
            if not stats or stats["count"] == 0:
                continue

            avg = round(stats["sum"] / stats["count"], 2) if stats["count"] > 0 else 0.0
            chart_data.append({
                "region": region,
                "timestamp": quake_time.isoformat(),
                "average": avg,
                "count": stats["count"]
            })

        chart_data.sort(key=lambda x: x['timestamp'])
        print(f"[INFO] {quake.place} (M{quake.magnitude}) traité | Moyenne fenêtre={window_avg} | Clé={region_key}")

        if region_key not in top_k_by_region:
            top_k_by_region[region_key] = []
        
        quake_info = {
            "place": quake.place,
            "magnitude": round(quake.magnitude, 2),
            "latitude": quake.latitude,
            "longitude": quake.longitude,
            "time": quake_time.isoformat(),
            "region": region_key
        }
        
        top_k_by_region[region_key] = update_top_k(
            top_k_by_region[region_key],
            (quake.magnitude, quake_info),
            K_REGION
        )

        quake_time = quake.time
        if isinstance(quake_time, str):
            quake_time = datetime.fromisoformat(quake_time)
        
        foreshock_metrics = update_foreshock_metric(
            region_key,
            quake_time)

        if foreshock_metrics["score"] > 0.7:
             print(
                 f"[FORESHOCK] Activité précurseur détectée en {region_key} "
                 f"(score={foreshock_metrics['score']})"
             )

        #MAGNITUDE TREND
        mag_trend = update_magnitude_trend(
            region_key,
            quake.magnitude,
            quake_time
        )

        if mag_trend["score"] > 0.7:
            print(
                f"[TREND] Magnitudes ascendantes en {region_key} "
                f"(slope={mag_trend['slope']}, score={mag_trend['score']})"
            )

        #ENERGY RELEASE
        energy_metrics = update_energy_metric(
            region_key,
            quake.magnitude,
            quake_time
        )

        if energy_metrics["score"] > 0.7:
            print(
                f"[ENERGY] Libération d'énergie anormale en {region_key} "
                f"(score={energy_metrics['score']})"
            )


        #CLUSTER SPATIAL (localisation de rupture)
        cluster_metrics = update_spatial_cluster(
            region_key,
            quake.latitude,
            quake.longitude,
            quake_time
        )

        cluster_id = f"{region_key}:{cluster_metrics['grid_cell']}"  # pour asy/aftershock
        migration_id = region_key  # pour migration spatiale

        if cluster_metrics["score"] > 0.7:
            print(
                f"[CLUSTER] Concentration spatiale anormale en {region_key} "
                f"(cell={cluster_metrics['grid_cell']}, "
                f"events={cluster_metrics['event_count']}, "
                f"score={cluster_metrics['score']})"
            )


        # SIGNAUX CLUSTER (dynamique locale)
        #AFTERSHOCK
        aftershock_metrics = update_aftershock_metric(
            cluster_id,
            quake.magnitude,
            quake_time
        )

        if aftershock_metrics["score"] > 0.7:
            print(
                f"[AFTERSHOCK] Activité post-séisme anormale en {cluster_id} "
                f"(score={aftershock_metrics['score']})"
            )

        #ASYMMETRY (accélération temporelle)
        asy_metrics = update_asymmetry_metric(
            cluster_id,
            quake_time
        )

        if asy_metrics["score"] > 0.7:
            print(
                f"[ASY] Accélération temporelle détectée en {cluster_id} "
                f"(ratio={asy_metrics['ratio']}, score={asy_metrics['score']})"
            )

        #MIGRATION SPATIALE
        migration = update_spatial_migration(
            migration_id,
            quake.latitude,
            quake.longitude,
            quake_time
        )

        if migration["score"] > 0.6:
            print(
                f"[MIGRATION] Déplacement spatial détecté en {region_key} "
                f"(cell={cluster_metrics['grid_cell']}, "
                f"distance={migration['distance_km']} km, "
                f"score={migration['score']})"
            )


        #FUSION DES SIGNAUX (alerte synthétique)
        fusion = fuse_signals({
            "foreshock": foreshock_metrics["score"],
            "trend": mag_trend["score"],
            "energy": energy_metrics["score"],
            "cluster": cluster_metrics["score"],
            "aftershock": aftershock_metrics["score"],
            "asy": asy_metrics["score"],
            "migration": migration["score"]
        })

        if fusion["level"] == "ALERT":
            print(
                f"[ALERTE SISMIQUE] {region_key} | "
                f"score={fusion['global_score']} | "
                f"signaux forts={fusion['strong_signals']}"
            )

        elif fusion["level"] == "VIGILANCE":
            print(
                f"[VIGILANCE SISMIQUE] {region_key} | "
                f"score={fusion['global_score']}"
            )
        #FUSION AVEC MACHINE LEARNING (score d'anomalie)
        ml_features = [
            foreshock_metrics["score"],
            mag_trend["score"],
            energy_metrics["score"],
            asy_metrics["score"],
            cluster_metrics["score"],
            migration["score"] if migration else 0.0
        ]
        ml_result = update_ml_anomaly_score(ml_features)
        if ml_result["ready"]:
            print(
                f"[ML] score={ml_result['score']} "
                f"| features={ml_features}"
            )
        else:
            print("[ML] En attente d'entraînement...")


last_points_hash = {}

# @app.timer(interval=20.0)
# async def compute_clusters():
#     """
#     Calcul des clusters DBSCAN
#     """
#     clusters_snapshot = []
#     regions = active_regions_list["regions"]

#     for region in regions:
#         points = seismic_points_flat.get(region, [])

#         if len(points) >= 3:

#             current_hash = hashlib.md5(json.dumps(points, sort_keys=True).encode()).hexdigest()

#             if last_points_hash.get(region) != current_hash:

#                 last_points_hash[region] = current_hash
#                 clusters = cluster_earthquakes(points)

#                 for cluster in clusters:
#                     clusters_snapshot.append({
#                         "region": region,
#                         "size": len(cluster),
#                         "avg_magnitude": round(
#                             sum(p["mag"] for p in cluster) / len(cluster), 2
#                         ),
#                         "points": cluster,
#                     })

#     clusters_snapshot_dict["latest"] = clusters_snapshot


@app.timer(interval=20.0)
async def compute_clusters_incremental():
    """
    Snapshot des clusters toutes les 20 secondes (à partir des modèles incrémentaux)
    """

    clusters_snapshot = []

    for region in active_regions_list["regions"]:
        clusters = get_clusters_from_model(region)
        clusters_snapshot.extend(clusters)

    clusters_snapshot_dict["latest"] = clusters_snapshot

def generate_chart_data(regions=None, max_quakes_per_region=10):
    if regions is None:
        regions = ["Europe", "Asie", "Amérique", "Afrique"]

    chart_data = []
    now = datetime.utcnow()
