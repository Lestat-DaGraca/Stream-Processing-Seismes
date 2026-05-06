import os
import sys
import time
from tracemalloc import start
import folium
from folium.plugins import MarkerCluster
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.metrics import silhouette_score, davies_bouldin_score,calinski_harabasz_score
from incdbscan import IncrementalDBSCAN

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'faust_app')))

from tables import clusters_snapshot_dict, seismic_points_flat, active_regions_list
from models.dbscan_seismic import cluster_earthquakes

def plot_k_distance(csv_path, min_samples=5):
    df = pd.read_csv(csv_path)
    df = df.dropna(subset=["latitude", "longitude", "mag"])

    coords = df[["latitude", "longitude"]].values

    neighbors = NearestNeighbors(n_neighbors=min_samples)
    neighbors_fit = neighbors.fit(coords)
    distances, _ = neighbors_fit.kneighbors(coords)

    k_distances = np.sort(distances[:, -1])

    plt.figure()
    plt.plot(k_distances)
    plt.ylim(0, 1)
    plt.xlabel("Points triés")
    plt.ylabel(f"{min_samples}-th distance")
    plt.title("Graphique k-distance (choix eps)")
    plt.show()

def test_clustering_from_csv(csv_path, eps_km=50, min_samples=5, show_table=True):

    df = pd.read_csv(csv_path)
    df = df.dropna(subset=["latitude", "longitude", "mag"])

    points = [
        {"lat": row["latitude"], "lon": row["longitude"], "mag": row["mag"]}
        for _, row in df.iterrows()
    ]

    if len(points) < min_samples:
        print("❌ Pas assez de points")
        return

    #Performance
    start = time.time()

    dbscan_clusters = cluster_earthquakes(
        points,
        eps_km=eps_km,
        min_samples=min_samples
    )

    end = time.time()
    execution_time = round(end - start, 4)

    #Stats
    cluster_sizes = [len(c) for c in dbscan_clusters]
    points_used = sum(cluster_sizes)
    noise_points = len(points) - points_used

    #Labels pour métriques
    labels = [-1] * len(points)

    for cluster_id, cluster in enumerate(dbscan_clusters):
        for p in cluster:
            idx = points.index(p)
            labels[idx] = cluster_id

    coords_array = np.array([[p["lat"], p["lon"]] for p in points])
    labels_array = np.array(labels)

    mask = labels_array != -1

    if len(set(labels)) > 1 and np.sum(mask) > 0:
        try:
            silhouette = silhouette_score(coords_array[mask], labels_array[mask])
            db_index = davies_bouldin_score(coords_array[mask], labels_array[mask])
            ch_score = calinski_harabasz_score(coords_array[mask], labels_array[mask])
        except:
            silhouette, db_index, ch_score = 0, 0, 0
    else:
        silhouette, db_index, ch_score = 0, 0, 0

    results = {
        "clusters": len(dbscan_clusters),
        "noise_points": noise_points,
        "avg_cluster_size": round(np.mean(cluster_sizes), 2) if cluster_sizes else 0,
        "silhouette": round(silhouette, 3),
        "davies_bouldin": round(db_index, 3),
        "calinski_harabasz": round(ch_score, 3),
        "execution_time_sec": execution_time
    }

    if show_table:
        return pd.DataFrame([results])
    else:
        print(results)

    return results

def benchmark_dbscan(csv_path):

    eps_values = [20, 50, 100]
    min_samples_values = [3, 5, 8]

    all_results = []

    for eps in eps_values:
        for min_samples in min_samples_values:

            print(f"\nTest eps={eps}, min_samples={min_samples}")

            result_df = test_clustering_from_csv(
                csv_path,
                eps_km=eps,
                min_samples=min_samples,
                show_table=True
            )

            result_df["eps"] = eps
            result_df["min_samples"] = min_samples

            all_results.append(result_df)

    final_df = pd.concat(all_results)

    print("BENCHMARK GLOBAL")
    print(final_df)

    return final_df

def plot_performance(df):
    plt.figure()

    for eps in df["eps"].unique():
        subset = df[df["eps"] == eps]
        plt.plot(subset["min_samples"], subset["execution_time_sec"], label=f"eps={eps}")

    plt.xlabel("min_samples")
    plt.ylabel("Temps (sec)")
    plt.title("Performance DBSCAN")
    plt.legend()
    plt.show()

def plot_map(csv_path, eps_km=50, min_samples=5):

    df = pd.read_csv(csv_path)
    df = df.dropna(subset=["latitude", "longitude", "mag"])

    points = [
        {"lat": row["latitude"], "lon": row["longitude"], "mag": row["mag"]}
        for _, row in df.iterrows()
    ]

    clusters = cluster_earthquakes(points, eps_km=eps_km, min_samples=min_samples)

    m = folium.Map(location=[0, 0], zoom_start=2)

    colors = ['red', 'blue', 'green', 'purple', 'orange']

    for i, cluster in enumerate(clusters):
        marker_cluster = MarkerCluster(name=f"Cluster {i}").add_to(m)
        color = colors[i % len(colors)]

        for p in cluster:
            folium.CircleMarker(
                location=[p['lat'], p['lon']],
                radius=4,
                color=color,
                fill=True
            ).add_to(marker_cluster)

    m.save("earthquake_clusters.html")

def read_csv_points(csv_path):
    df = pd.read_csv(csv_path)
    df = df.dropna(subset=["latitude", "longitude", "mag"])
    points = [{"lat": row["latitude"], "lon": row["longitude"], "mag": row["mag"]} for _, row in df.iterrows()]
    coords = np.array([[p["lat"], p["lon"]] for p in points])
    return points, coords

def evaluate_clusters(points, labels):
    coords = np.array([[p["lat"], p["lon"]] for p in points])
    labels_array = np.array(labels)
    mask = labels_array != -1
    if len(set(labels)) > 1 and np.sum(mask) > 0:
        silhouette = silhouette_score(coords[mask], labels_array[mask])
        db_index = davies_bouldin_score(coords[mask], labels_array[mask])
        ch_score = calinski_harabasz_score(coords[mask], labels_array[mask])
    else:
        silhouette, db_index, ch_score = 0, 0, 0
    return silhouette, db_index, ch_score



def cluster_dbscan_classic(points, eps_km=50, min_samples=5):
    start = time.time()
    clusters = cluster_earthquakes(points, eps_km=eps_km, min_samples=min_samples)
    end = time.time()
    exec_time = end - start
    return clusters, exec_time

def cluster_dbscan_incremental(points, eps_km=50, min_samples=5):
    coords = np.array([[p["lat"], p["lon"]] for p in points])
    eps_deg = eps_km / 111.0
    inc_db = IncrementalDBSCAN(eps=eps_deg, min_pts=min_samples)
    
    start = time.time()
    inc_db.insert(coords)
    
    labels = inc_db.get_cluster_labels(coords)
    end = time.time()
    exec_time = end - start

    # Regrouper les points en clusters
    clusters_dict = {}
    for label, point in zip(labels, points):
        if label == -1 or np.isnan(label):
            continue
        clusters_dict.setdefault(int(label), []).append(point)
    
    clusters = list(clusters_dict.values())
    return clusters, exec_time

# Évaluer les clusters
def evaluate_clusters(points, clusters):
    labels = [-1] * len(points)
    for cluster_id, cluster in enumerate(clusters):
        for p in cluster:
            idx = points.index(p)
            labels[idx] = cluster_id

    coords = np.array([[p["lat"], p["lon"]] for p in points])
    labels_array = np.array(labels)
    mask = labels_array != -1

    if len(set(labels)) > 1 and np.sum(mask) > 0:
        silhouette = silhouette_score(coords[mask], labels_array[mask])
        db_index = davies_bouldin_score(coords[mask], labels_array[mask])
        ch_score = calinski_harabasz_score(coords[mask], labels_array[mask])
    else:
        silhouette, db_index, ch_score = 0, 0, 0

    return silhouette, db_index, ch_score

# Benchmark global
def benchmark(csv_path, eps_km=50, min_samples=5):
    points, coords = read_csv_points(csv_path)
    print(f"Nombre de séismes : {len(points)}")

    # DBSCAN classique
    clusters_classic, time_classic = cluster_dbscan_classic(points, eps_km, min_samples)
    silhouette, db_index, ch_score = evaluate_clusters(points, clusters_classic)
    print("\n--- DBSCAN classique ---")
    print(f"Temps : {time_classic:.4f} sec | Silhouette : {silhouette:.3f} | DB : {db_index:.3f} | CH : {ch_score:.3f}")

    # IncrementalDBSCAN
    clusters_inc, time_inc = cluster_dbscan_incremental(points, eps_km, min_samples)
    silhouette_inc, db_index_inc, ch_score_inc = evaluate_clusters(points, clusters_inc)
    print("\n--- IncrementalDBSCAN ---")
    print(f"Temps : {time_inc:.4f} sec | Silhouette : {silhouette_inc:.3f} | DB : {db_index_inc:.3f} | CH : {ch_score_inc:.3f}")

    # Comparaison
    print("\n--- Comparaison des performances ---")
    print(f"DBSCAN classique : {time_classic:.4f} sec")
    print(f"IncrementalDBSCAN : {time_inc:.4f} sec")
    print(f"Gain de temps : {time_classic/time_inc:.2f}x plus rapide avec IncrementalDBSCAN")

    return {
        "classic": {"time": time_classic, "silhouette": silhouette, "db_index": db_index, "ch_score": ch_score},
        "incremental": {"time": time_inc, "silhouette": silhouette_inc, "db_index": db_index_inc, "ch_score": ch_score_inc}
    }


if __name__ == "__main__":

    CSV_PATH = "producers/data/all_month.csv"

    plot_k_distance(CSV_PATH, min_samples=5)
    df_results = benchmark_dbscan(CSV_PATH)
    plot_performance(df_results)
    plot_map(CSV_PATH, eps_km=50, min_samples=5)

    benchmark(CSV_PATH)