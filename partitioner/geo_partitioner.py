import hashlib

def geo_partitioner(key_bytes, all_partitions, available_partitions):
    """
    Partitioner Kafka basé sur une clé géographique.
    """
    if key_bytes is None:
        return all_partitions[0]

    key_hash = int(hashlib.sha256(key_bytes).hexdigest(), 16)
    return all_partitions[key_hash % len(all_partitions)]

def detect_geographical_zone(lat: float, lon: float) -> str:
    """
    Détermine une grande zone géographique à partir des coordonnées (latitude, longitude).
    """
    if lat is None or lon is None:
        return "Unknown"

    if lat < -60:
        return "Antarctica"
    elif lat > 0 and -170 < lon < -30:
        return "NorthAmerica"
    elif lat < 0 and -90 < lon < -30:
        return "SouthAmerica"
    elif lat > 35 and -30 < lon < 60:
        return "Europe"
    elif lat < 35 and -20 < lon < 50:
        return "Africa"
    elif lat > -10 and 60 < lon < 150:
        return "Asia"
    elif lat < 0 and 110 < lon < 180:
        return "Oceania"
    else:
        return "Unknown"
