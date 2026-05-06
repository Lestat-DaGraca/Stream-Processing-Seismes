import json
import time
import random
from datetime import datetime
from kafka import KafkaProducer

KAFKA_BROKER = "localhost:9092"
TOPIC = "earthquakes"

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKER,
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)

REGIONS = ["EUROPE", "ASIA", "NORTH_AMERICA"]

def generate_event():
    return {
        "id": random.randint(100000, 999999),
        "region": random.choice(REGIONS),
        "magnitude": round(random.uniform(1.0, 7.0), 1),
        "timestamp_production": datetime.utcnow().isoformat()
    }

def run_test(messages_per_second=1000, duration_seconds=30):
    print(f"Test démarré : {messages_per_second} msg/s pendant {duration_seconds}s")

    total_sent = 0
    start_time = time.time()

    for second in range(duration_seconds):
        second_start = time.time()

        for _ in range(messages_per_second):
            event = generate_event()

            producer.send(
                TOPIC,
                key=event["region"].encode("utf-8"),
                value=event
            )
            total_sent += 1

        elapsed = time.time() - second_start
        if elapsed < 1:
            time.sleep(1 - elapsed)

        print(f"Envoyé : {(second + 1) * messages_per_second} messages")

    producer.flush()

    total_time = time.time() - start_time
    print("\n--- Résultats ---")
    print(f"Messages envoyés : {total_sent}")
    print(f"Temps total : {total_time:.2f}s")
    print(f"Débit réel : {total_sent / total_time:.2f} msg/s")


if __name__ == "__main__":
    run_test(messages_per_second=5000, duration_seconds=60)