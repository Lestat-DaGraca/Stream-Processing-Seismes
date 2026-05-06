from app import app, latest_quakes
from tables import stats_table, latest_trends, clusters_snapshot_dict
from agents import top_k_by_region, K_GLOBAL, all_earthquakes
from datetime import datetime

# Import de la logique de clustering incrémental
from kmeans import (
    do_full_clustering,
    process_incremental_updates,
    should_do_full_reclustering, 
    prepare_clustering_response,
    kmeans_state,
    update_signal  
)


@app.page("/data")
async def data_api(self, request):
    """Retourne les données des derniers séismes"""
    return self.json(latest_quakes)

@app.page("/stats/global")
async def global_stats_api(self, request):
    """Retourne les statistiques globales des séismes"""
    global_stats = stats_table.get('global', {"sum": 0.0, "count": 0})
    
    avg_global = (
        round(global_stats["sum"] / global_stats["count"], 2)
        if global_stats["count"] > 0 else 0.0
    )
    
    return self.json({
        "sum": global_stats["sum"],
        "count": global_stats["count"],
        "average": avg_global
    })

@app.page("/stats/trends")
async def trends_api(self, request):
    """Retourne les dernières tendances des séismes"""
    return self.json(latest_trends.get('snapshot', []))

@app.page("/stats/topk/global")
async def top_k_global_api(self, request):
    """
    Retourne le top K_GLOBAL des séismes par magnitude globalement.
    Calculé à la volée en fusionnant les heaps de chaque région.
    """
    all_quakes = [item for heap in top_k_by_region.values() for item in heap]
    sorted_top_k = sorted(all_quakes, key=lambda x: x[0], reverse=True)[:K_GLOBAL]

    result = [
        {
            "rank": idx + 1,
            "magnitude": item[0],
            **item[2]
        }
        for idx, item in enumerate(sorted_top_k)
    ]

    return self.json(result)

@app.page("/stats/topk/region")
async def top_k_by_region_api(self, request):
    """Retourne le top 5 des séismes par magnitude pour chaque région"""
    result = {}
    
    for region, heap in top_k_by_region.items():
        sorted_region = sorted(heap, key=lambda x: x[0], reverse=True)
        result[region] = [
            {
                "rank": idx + 1,
                "magnitude": item[0],
                **item[2]
            }
            for idx, item in enumerate(sorted_region)
        ]
    
    return self.json(result)

@app.page("/stats/topk/region/<region_name>")
async def top_k_specific_region_api(self, request, region_name):
    """Retourne le top 5 d'une région spécifique"""
    heap = top_k_by_region.get(region_name, [])
    sorted_region = sorted(heap, key=lambda x: x[0], reverse=True)
    
    result = [
        {
            "rank": idx + 1,
            "magnitude": item[0],
            **item[2]
        }
        for idx, item in enumerate(sorted_region)
    ]
    
    return self.json(result)

@app.page("/clusters")
async def clusters_api(self, request):
    """Retourne les clusters de séismes DBSCAN"""
    clusters = clusters_snapshot_dict.get("latest", [])
    
    enriched_clusters = []
    for idx, cluster in enumerate(clusters):
        if cluster["points"]:
            center_lat = sum(p["lat"] for p in cluster["points"]) / len(cluster["points"])
            center_lon = sum(p["lon"] for p in cluster["points"]) / len(cluster["points"])
            
            enriched_clusters.append({
                "id": idx,
                "region": cluster["region"],
                "size": cluster["size"],
                "avg_magnitude": cluster["avg_magnitude"],
                "center": [center_lat, center_lon],
                "points": cluster["points"]
            })

    return self.json(enriched_clusters)

@app.page("/kmeans/earthquakes")
async def kmeans_earthquakes_api(self, request):
    """Retourne tous les séismes pour la page K-Means"""
    return self.json(all_earthquakes)

@app.page("/kmeans/cluster")
async def kmeans_cluster_api(self, request):
    """
    Applique K-Means (complet ou retourne l'état actuel)
    
    Query params:
        - k: nombre de clusters (défaut: 3)
        - force_full: force un clustering complet (défaut: false)
    """
    k = int(request.query.get('k', 3))
    force_full = request.query.get('force_full', 'false').lower() == 'true'
    
    if len(all_earthquakes) < 3:
        return self.json({
            "error": f"Minimum 3 séismes requis ({len(all_earthquakes)}/3)"
        })
    
    if force_full or should_do_full_reclustering() or kmeans_state.n_clusters != k:
        result = do_full_clustering(all_earthquakes, k)
        if result is None:
            return self.json({"error": "Clustering failed"})
        result["clustering_type"] = "full"
        return self.json(result)
    
    result = prepare_clustering_response()
    result["clustering_type"] = "current_state"
    return self.json(result)


@app.page("/kmeans/update")
async def kmeans_update_api(self, request):
    """
    Endpoint pour mise à jour incrémentale.
    Vérifie s'il y a de nouveaux séismes et les ajoute au clustering.
    """
    result = process_incremental_updates(all_earthquakes)
    update_signal.reset()
    return self.json(result)


@app.page("/kmeans/wait-for-update")
async def kmeans_wait_for_update_api(self, request):
    """
    Endpoint de long polling : attend qu'un nouveau séisme arrive.
    Timeout après 120 secondes.
    """
    has_update = await update_signal.wait_for_update(timeout=120)
    
    return self.json({
        "has_update": has_update,
        "total_earthquakes": len(all_earthquakes),
        "timestamp": datetime.now().isoformat()
    })