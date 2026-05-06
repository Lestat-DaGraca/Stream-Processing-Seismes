from pydantic import BaseModel
from faust import Record

class EarthquakeEvent(Record, serializer='json'):
    """
    Représente un événement sismique.
    """
    id: str
    time: str
    latitude: float
    longitude: float
    depth: float
    magnitude: float
    place: str
    status: str
    url: str
    source: str = "usgs"


# Modèle pour la requête rectangle
class RectangleParams(BaseModel):
    minlatitude: float
    maxlatitude: float
    minlongitude: float
    maxlongitude: float
    minmagnitude: float
    maxmagnitude: float
    mindepth: float
    maxdepth: float
    starttime: str
    endtime: str
    eventtype: str = "earthquake"
    format: str = "geojson"
    orderby: str = "time"

# Modèle pour la requête cercle
class CircleParams(BaseModel):
    latitude: float
    longitude: float
    maxradiuskm: float
    minmagnitude: float
    maxmagnitude: float
    mindepth: float
    maxdepth: float
    starttime: str
    endtime: str
    eventtype: str = "earthquake"
    format: str = "geojson"
    orderby: str = "time"
