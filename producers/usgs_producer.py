import os
import json
import time
from kafka import KafkaProducer
import pandas as pd

from models.earthquake import EarthquakeEvent
from .utils import fetch_usgs_events, normalize_event
from dotenv import load_dotenv
from partitioner.geo_partitioner import geo_partitioner, detect_geographical_zone
import threading

load_dotenv()

USGS_FEEDS = {
    "last_hour": os.getenv("USGS_API_FLUX_GEOJSON"),
    "last_day": os.getenv("USGS_LAST_DAY"),
    "significant_week": os.getenv("USGS_SIGNIFICANT_WEEK"),
    "m4_5_day": os.getenv("USGS_M4_5_DAY")
}

TOPICS = os.getenv("KAFKA_TOPIC").split(",")

class USGSProducer:
    def __init__(self, topic: str, source_url: str, partitioned: bool = False):
        self.broker : str = os.getenv("KAFKA_BROKER")
        self.topic : str = topic
        self.source_url : str = source_url
        self.partitioned : bool = partitioned

        self.already_sent_ids = set()

        if self.partitioned:
            self.producer = KafkaProducer(
                bootstrap_servers=[self.broker],
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                partitioner=geo_partitioner
            )
        else:
            self.producer = KafkaProducer(
                bootstrap_servers=[self.broker],
                value_serializer=lambda v: json.dumps(v).encode("utf-8")
            )

    def get_partition_key(self, event: dict) -> bytes:
        """
        Détermine la zone géographique du séisme à partir de ses coordonnées.
        """
        coords = event.get("geometry", {}).get("coordinates", [None, None])
        lon, lat = coords[0], coords[1]
        zone = detect_geographical_zone(lat, lon)
        return zone.encode("utf-8")
    
    def send_events(self):
        """
        Récupère les événements USGS et les envoie sur Kafka.
        """
        events : list = fetch_usgs_events()

        for event in events:
            event_id = event.get("id")
            if event_id not in self.already_sent_ids:
                normalized : dict = normalize_event(event)
                key : bytes = self.get_partition_key(event)

                if self.partitioned:
                    key = self.get_partition_key(event)
                    self.producer.send(self.topic, value=normalized, key=key).add_callback(self.on_send_success).add_errback(self.on_send_error)
                    print(f"[INFO] Envoi de l'événement {normalized} sur le topic {self.topic} avec la clé {key.decode('utf-8')}")
                else:
                    self.producer.send(self.topic, value=normalized).add_callback(self.on_send_success).add_errback(self.on_send_error)

                self.already_sent_ids.add(event_id)
                self.producer.flush()

    def run_loop(self, interval: int):
        """
        Boucle infinie pour envoyer les événements
        """
        while True:
            try:
                self.send_events()
            except Exception as e:
                print(f"[ERREUR] {e} : recommence dans {interval}s")
            time.sleep(interval)
    
    def on_send_success(self, record_metadata):
        print(f"[SUCCÈS] Message envoyé à {record_metadata.topic} partition {record_metadata.partition} offset {record_metadata.offset}")

    def on_send_error(self, excp):
        print(f"[ERREUR] Échec de l'envoi du message : {excp}")

    def send_csv_events(self, csv_path: str, delay: float = 0.0, limit=None, randomize=True):

        df = pd.read_csv(csv_path)
        df = df.dropna(subset=["latitude", "longitude", "mag"])

        if limit:
            df = df.sample(limit) if randomize else df.head(limit)

        print(f"🚀 CSV → Kafka ({len(df)} événements)")

        timestamp = int(time.time() * 1000)

        for idx, row in df.iterrows():

            unique_id = f"csv-{idx}-{timestamp}"

            earthquake = EarthquakeEvent(
                id=unique_id,
                time=row.get("time", None),
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                depth=float(row.get("depth", 0.0)),
                magnitude=float(row["mag"]),
                place=row.get("place", "CSV Source"),
                status="csv://local",
                source="csv",
                url="csv://local"
            )

            payload = earthquake.asdict()

            key = detect_geographical_zone(
                payload["latitude"],
                payload["longitude"]
            ).encode("utf-8")

            if self.partitioned:
                self.producer.send(
                    self.topic,
                    value=payload,
                    key=key
                ).add_callback(self.on_send_success).add_errback(self.on_send_error)
            else:
                self.producer.send(
                    self.topic,
                    value=payload
                ).add_callback(self.on_send_success).add_errback(self.on_send_error)

            if delay > 0:
                time.sleep(delay)

        self.producer.flush()

producers = [
    USGSProducer(topic=TOPICS[0], source_url=USGS_FEEDS["last_hour"], partitioned=False),
    USGSProducer(topic=TOPICS[1], source_url=USGS_FEEDS["last_hour"], partitioned=True),
    USGSProducer(topic=TOPICS[2], source_url=USGS_FEEDS["last_day"], partitioned=False),
    USGSProducer(topic=TOPICS[3], source_url=USGS_FEEDS["significant_week"], partitioned=False),
]
# Script pour tester le producer
if __name__ == "__main__":
    threads = []
    
    for producer in producers:
        t = threading.Thread(target=producer.run_loop, args=(10,), daemon=True)
        t.start()
        threads.append(t)
        #if producer.topic == TOPICS[1]:
            #producer.send_csv_events("producers/data/all_month.csv", delay=0.01)

    while True:
        time.sleep(10)