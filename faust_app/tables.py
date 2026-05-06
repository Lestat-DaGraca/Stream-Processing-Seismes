from collections import deque
from app import app

#Table à fenêtre glissante pour le suivi des statistiques des séismes
windowed_stats = app.Table('windowed_stats', default=lambda: {"sum": 0.0, "count": 0}, partitions=8).hopping(size=600, step=120, key_index=True)

#Table globale accumulant les statistiques (somme magnitudes et nombre total) depuis le lancement
stats_table = app.Table('stats', default=lambda: {"sum": 0.0, "count": 0}, partitions=1)

#Similaire à stats_table mais segmentée par région (clé = nom de la région) partitions=8 pour permettre un traitement parallèle par région
stats_table_by_region = app.Table('stats_by_region', default=lambda: {"sum": 0.0, "count": 0}, partitions=8)

#Stocke les résultats finaux du clustering
clusters_table = app.Table("clusters_table", default=list, partitions=1)

#Buffer de points sismiques fenêtré (1h de données, mis à jour toutes les 5 min) source de données pour l'algorithme de clustering (DBSCAN a besoin d'un historique)
seismic_points = app.Table("seismic_points", default=list, partitions=8).hopping(size=3600, step=300)

#(sans fenêtre temporelle) points sismiques pour un accès rapideaux coordonnées brutes traitées par les partitions
seismic_points_flat = app.Table("seismic_points_flat", default=deque, partitions=8)

#Dictionnaire (clé: région, valeur: booléen) pour savoir si une région a eu un séisme récemment.
active_regions = app.Table("active_regions", default=bool, partitions=8)

#Table à partition unique listant uniquement les noms des régions actuellement actives
active_regions_list = app.Table("active_regions_list", default=list, partitions=1)

#Stocke les dernières tendances calculées pour affichage dashboard
latest_trends = app.Table('latest_trends', default=list, partitions=1)

#Fenêtre glissante pour le suivi des statistiques des séismes par régions pour les 10 dernière minutes
windowed_region_counts = (app.Table('windowed_region_counts', default=int, partitions=1,).hopping(size=600, step=120, expires=900, key_index=True))

#Variable pour garder en mémoire la dernière snapshot des clusters et répondre instantanément aux requêtes API sans recalculer
clusters_snapshot_dict = {"latest": []}