from sklearn.cluster import KMeans
import numpy as np
from datetime import datetime, timedelta
import asyncio

#CONFIGURATION
FULL_RECLUSTERING_INTERVAL = timedelta(minutes=20)  # Reclustering complet toutes les 20 min
THRESHOLD_TINY_MOVE = 0.02   # 2% - si centroïde bouge moins, on ignore
#entre les deux on recalcule le cluster
THRESHOLD_BIG_MOVE = 0.10    # 10% - si centroïde bouge plus, on relance tout


#SIGNALISATION POUR LONG POLLING
class UpdateSignal:
    """Gère la signalisation des nouveaux séismes pour le long polling"""
    
    def __init__(self):
        self.has_new_earthquake = False
        self.waiting_futures = []  # Liste des futures en attente
    
    def notify_new_earthquake(self):
        """Signale qu'un nouveau séisme est arrivé"""
        self.has_new_earthquake = True
        # Réveiller toutes les requêtes en attente
        for future in self.waiting_futures:
            if not future.done():
                future.set_result(True)
        self.waiting_futures.clear()
    
    def reset(self):
        """Reset le flag après que le frontend a récupéré la mise à jour"""
        self.has_new_earthquake = False
    
    async def wait_for_update(self, timeout=120):
        """
        Attend qu'un nouveau séisme arrive (ou timeout)
        
        Args:
            timeout: Temps max d'attente en secondes
        
        Returns:
            True si nouveau séisme, False si timeout
        """
        if self.has_new_earthquake:
            return True
        
        # Créer une future pour cette requête
        future = asyncio.Future()
        self.waiting_futures.append(future)
        
        try:
            # Attendre soit le signal, soit le timeout
            await asyncio.wait_for(future, timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            # Nettoyer
            if future in self.waiting_futures:
                self.waiting_futures.remove(future)


# Instance globale du signal
update_signal = UpdateSignal()


#ÉTAT DU CLUSTERING
class KMeansState:
    """Singleton pour stocker l'état du clustering"""
    
    def __init__(self):
        self.centroids = None           # Centroïdes actuels (numpy array)
        self.assignments = []           # Liste des assignations (cluster_id pour chaque séisme)
        self.n_clusters = 3             # Nombre de clusters
        self.last_full_clustering = None  # Timestamp du dernier clustering complet
        self.earthquakes_snapshot = []  # Snapshot des séismes au dernier clustering
    
    def reset(self):
        """Réinitialise l'état du clustering"""
        self.centroids = None
        self.assignments = []
        self.n_clusters = 3
        self.last_full_clustering = None
        self.earthquakes_snapshot = []


# Instance globale
kmeans_state = KMeansState()


#FONCTIONS UTILITAIRES

def calculate_centroid_shift(old_centroid, new_centroid):
    """
    Calcule le déplacement relatif d'un centroïde
    
    Args:
        old_centroid: Position précédente du centroïde
        new_centroid: Nouvelle position du centroïde
    
    Returns:
        float: Ratio de déplacement (0.0 à 1.0+)
    """
    distance = np.linalg.norm(new_centroid - old_centroid)
    # Normaliser par la norme du centroïde pour avoir un %
    norm = np.linalg.norm(old_centroid)
    if norm < 1e-10:  # Éviter division par 0
        return 0.0
    return distance / norm


def find_closest_cluster(point, centroids):
    """
    Trouve le cluster le plus proche d'un point
    
    Args:
        point: Coordonnées du point [lat, lon]
        centroids: Liste des centroïdes
    
    Returns:
        int: Index du cluster le plus proche
    """
    distances = [np.linalg.norm(point - c) for c in centroids]
    return int(np.argmin(distances))


# ========== LOGIQUE DE CLUSTERING ==========

def should_do_full_reclustering():
    """
    Vérifie si on doit faire un reclustering complet (toutes les 20 min)
    
    Returns:
        bool: True si un reclustering complet est nécessaire
    """
    if kmeans_state.last_full_clustering is None:
        return True
    
    elapsed = datetime.now() - kmeans_state.last_full_clustering
    return elapsed >= FULL_RECLUSTERING_INTERVAL


def incremental_kmeans_update(new_earthquake):
    """
    Ajoute un nouveau séisme au clustering existant avec propagation intelligente
    
    Args:
        new_earthquake: dict avec 'latitude', 'longitude', etc.
    
    Returns:
        dict: Informations sur la mise à jour (cluster assigné, déplacement, propagation)
        None: Si pas de clustering existant
    """
    # Si pas de clustering existant, on force un clustering complet
    if kmeans_state.centroids is None:
        return None
    
    new_point = np.array([new_earthquake['latitude'], new_earthquake['longitude']])
    
    # 1. Trouver le cluster le plus proche
    cluster_id = find_closest_cluster(new_point, kmeans_state.centroids)
    
    # 2. Ajouter le point
    kmeans_state.assignments.append(cluster_id)
    kmeans_state.earthquakes_snapshot.append(new_earthquake)
    
    # 3. Recalculer le centroïde du cluster modifié
    old_centroid = kmeans_state.centroids[cluster_id].copy()
    
    # Points du cluster
    cluster_points = [
        np.array([kmeans_state.earthquakes_snapshot[i]['latitude'], 
                  kmeans_state.earthquakes_snapshot[i]['longitude']])
        for i, c in enumerate(kmeans_state.assignments) 
        if c == cluster_id
    ]
    
    new_centroid = np.mean(cluster_points, axis=0)
    kmeans_state.centroids[cluster_id] = new_centroid
    
    # 4. Calculer le déplacement
    shift_ratio = calculate_centroid_shift(old_centroid, new_centroid)
    
    changed_assignments = []
    
    # 5. Décider de la propagation
    if shift_ratio < THRESHOLD_TINY_MOVE:
        # Quasi aucun mouvement, on ne fait rien
        propagation_type = "none"
        
    elif shift_ratio < THRESHOLD_BIG_MOVE:
        # Mouvement moyen : on recalcule seulement les points de ce cluster
        propagation_type = "cluster_only"
        
        for i, assigned_cluster in enumerate(kmeans_state.assignments):
            if assigned_cluster == cluster_id:
                point = np.array([
                    kmeans_state.earthquakes_snapshot[i]['latitude'],
                    kmeans_state.earthquakes_snapshot[i]['longitude']
                ])
                new_cluster = find_closest_cluster(point, kmeans_state.centroids)
                
                if new_cluster != assigned_cluster:
                    kmeans_state.assignments[i] = new_cluster
                    changed_assignments.append(i)
        
        # Recalculer les centroïdes des clusters affectés
        affected_clusters = set([cluster_id] + [kmeans_state.assignments[i] for i in changed_assignments])
        for c in affected_clusters:
            cluster_points = [
                np.array([kmeans_state.earthquakes_snapshot[i]['latitude'], 
                          kmeans_state.earthquakes_snapshot[i]['longitude']])
                for i, assigned in enumerate(kmeans_state.assignments) 
                if assigned == c
            ]
            if cluster_points:
                kmeans_state.centroids[c] = np.mean(cluster_points, axis=0)
    
    else:
        # Gros mouvement : propagation complète avec itérations
        propagation_type = "full_propagation"
        max_iterations = 10
        
        for iteration in range(max_iterations):
            has_changed = False
            
            for i in range(len(kmeans_state.earthquakes_snapshot)):
                point = np.array([
                    kmeans_state.earthquakes_snapshot[i]['latitude'],
                    kmeans_state.earthquakes_snapshot[i]['longitude']
                ])
                old_cluster = kmeans_state.assignments[i]
                new_cluster = find_closest_cluster(point, kmeans_state.centroids)
                
                if new_cluster != old_cluster:
                    kmeans_state.assignments[i] = new_cluster
                    changed_assignments.append(i)
                    has_changed = True
            
            # Recalculer tous les centroïdes
            for c in range(kmeans_state.n_clusters):
                cluster_points = [
                    np.array([kmeans_state.earthquakes_snapshot[i]['latitude'], 
                              kmeans_state.earthquakes_snapshot[i]['longitude']])
                    for i, assigned in enumerate(kmeans_state.assignments) 
                    if assigned == c
                ]
                if cluster_points:
                    kmeans_state.centroids[c] = np.mean(cluster_points, axis=0)
            
            if not has_changed:
                break
    
    return {
        "cluster_assigned": cluster_id,
        "centroid_shift": float(shift_ratio),
        "propagation_type": propagation_type,
        "points_reassigned": len(set(changed_assignments))
    }


def do_full_clustering(all_earthquakes, k=None):
    """
    Effectue un clustering K-Means complet sur tous les séismes
    
    Args:
        all_earthquakes: Liste de tous les séismes disponibles
        k: Nombre de clusters (optionnel, utilise kmeans_state.n_clusters par défaut)
    
    Returns:
        dict: Résultat du clustering avec séismes, clusters, centres
        None: Si pas assez de données
    """
    if k is None:
        k = kmeans_state.n_clusters
    
    if len(all_earthquakes) < 3:
        return None
    
    if k > len(all_earthquakes):
        k = len(all_earthquakes)
    
    # Extraire coordonnées
    coords = np.array([[eq['latitude'], eq['longitude']] for eq in all_earthquakes])
    
    # K-Means
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = kmeans.fit_predict(coords)
    
    # Mettre à jour l'état
    kmeans_state.centroids = kmeans.cluster_centers_
    kmeans_state.assignments = labels.tolist()
    kmeans_state.n_clusters = k
    kmeans_state.last_full_clustering = datetime.now()
    kmeans_state.earthquakes_snapshot = [eq.copy() for eq in all_earthquakes]
    
    return prepare_clustering_response()


def prepare_clustering_response():
    """
    Prépare la réponse formatée avec les données de clustering actuelles
    
    Returns:
        dict: Données formatées pour l'API
    """
    earthquakes_with_clusters = []
    for idx, eq in enumerate(kmeans_state.earthquakes_snapshot):
        eq_copy = eq.copy()
        eq_copy['cluster'] = int(kmeans_state.assignments[idx])
        earthquakes_with_clusters.append(eq_copy)
    
    # Centres des clusters
    cluster_centers = [
        {
            "id": i,
            "latitude": float(kmeans_state.centroids[i][0]),
            "longitude": float(kmeans_state.centroids[i][1])
        }
        for i in range(kmeans_state.n_clusters)
    ]
    
    # Grouper par cluster pour statistiques
    clusters_stats = {}
    for eq in earthquakes_with_clusters:
        cluster_id = eq['cluster']
        if cluster_id not in clusters_stats:
            clusters_stats[cluster_id] = {
                "id": cluster_id,
                "count": 0,
                "earthquakes": [],
                "avg_magnitude": 0,
                "center": cluster_centers[cluster_id]
            }
        clusters_stats[cluster_id]["count"] += 1
        clusters_stats[cluster_id]["earthquakes"].append(eq)
    
    # Calculer magnitude moyenne par cluster
    for cluster_id, stats in clusters_stats.items():
        mags = [eq['magnitude'] for eq in stats['earthquakes']]
        stats['avg_magnitude'] = round(sum(mags) / len(mags), 2) if mags else 0
    
    return {
        "n_clusters": kmeans_state.n_clusters,
        "total_earthquakes": len(kmeans_state.earthquakes_snapshot),
        "earthquakes": earthquakes_with_clusters,
        "clusters": list(clusters_stats.values()),
        "centers": cluster_centers,
        "last_full_clustering": kmeans_state.last_full_clustering.isoformat() if kmeans_state.last_full_clustering else None
    }


def process_incremental_updates(all_earthquakes):
    """
    Traite tous les nouveaux séismes depuis la dernière mise à jour
    
    Args:
        all_earthquakes: Liste complète de tous les séismes
    
    Returns:
        dict: Résultat de la mise à jour (type, logs, données)
    """
    # Vérifier s'il faut faire un reclustering complet
    if should_do_full_reclustering():
        result = do_full_clustering(all_earthquakes)
        return {
            **result,
            "update_type": "full_reclustering",
            "reason": "20 minutes elapsed",
            "updates": []
        }
    
    # Vérifier s'il y a de nouveaux séismes
    current_count = len(kmeans_state.earthquakes_snapshot)
    total_count = len(all_earthquakes)
    
    if total_count <= current_count:
        # Pas de nouveaux séismes
        return {
            "update_type": "no_change",
            "total_earthquakes": current_count
        }
    
    # Ajouter les nouveaux séismes un par un
    new_earthquakes = all_earthquakes[current_count:]
    update_logs = []
    
    for new_eq in new_earthquakes:
        update_info = incremental_kmeans_update(new_eq)
        if update_info:
            update_logs.append({
                "earthquake": new_eq['place'],
                **update_info
            })
    
    # Retourner la réponse avec les mises à jour
    result = prepare_clustering_response()
    result["update_type"] = "incremental"
    result["updates"] = update_logs
    
    return result
