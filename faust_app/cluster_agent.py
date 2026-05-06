import pandas as pd
from partitioner.geo_partitioner import detect_geographical_zone
from tables import seismic_points_flat, active_regions_list

def load_csv_seismic_points(csv_path, limit=None):
    """Charge les points sismiques à partir d'un fichier CSV"""

    df = pd.read_csv(csv_path)
    df = df.dropna(subset=["latitude", "longitude", "mag"])

    if limit:
        df = df.head(limit)

    for _, row in df.iterrows():
        region = detect_geographical_zone(row["latitude"], row["longitude"])

        point = {
            "lat": row["latitude"],
            "lon": row["longitude"],
            "mag": row["mag"],
            "time": row.get("time", None)
        }

        seismic_points_flat.setdefault(region, []).append(point)

        if region not in active_regions_list["regions"]:
            active_regions_list["regions"].append(region)
