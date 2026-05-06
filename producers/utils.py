import requests
import os
from datetime import datetime
from dotenv import load_dotenv
from models.earthquake import EarthquakeEvent

load_dotenv()

USGS_FEED_URL = os.getenv("USGS_API_FLUX_GEOJSON")

def fetch_usgs_events():
    """
    Récupère les événements récents depuis le flux GeoJSON USGS.
    """
    response = requests.get(USGS_FEED_URL)
    response.raise_for_status()
    return response.json()["features"]

def normalize_event(event):
    """
    Transforme l'événement USGS en dictionnaire pour Kafka.
    """
    props = event["properties"]
    geometry = event["geometry"]["coordinates"]
    time_iso = datetime.utcfromtimestamp(props["time"] / 1000).isoformat()


    print("time_iso:", time_iso)

    earthquakeEvent = EarthquakeEvent(
        id = event["id"],
        time = time_iso,
        latitude = geometry[1],
        longitude = geometry[0],
        depth = geometry[2],
        magnitude = props["mag"],
        place = props["place"],
        status = props["url"],
        source = props.get("sources", "usgs"),
        url = props["url"],
    )
    
    return earthquakeEvent.asdict()
