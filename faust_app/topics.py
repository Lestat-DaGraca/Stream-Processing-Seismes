from app import app
from models.earthquake import EarthquakeEvent

#Topic pour les événements sismiques par région
usgs_by_region_topic = app.topic('usgs_by_region', value_type=EarthquakeEvent)

#Topic pour les événements sismiques globaux
earthquake_topic = app.topic('earthquakes', value_type=EarthquakeEvent)