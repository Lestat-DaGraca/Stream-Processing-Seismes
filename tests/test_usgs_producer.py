import unittest
from unittest.mock import patch, MagicMock, call
from datetime import datetime, timezone

from producers.usgs_producer import USGSProducer

class TestUSGSProducer(unittest.TestCase):
    @patch('producers.usgs_producer.fetch_usgs_events')
    @patch('producers.usgs_producer.normalize_event')
    @patch('producers.usgs_producer.KafkaProducer')
    def test_run_fetches_and_sends_events(self, mock_kafka_producer, mock_normalize_event, mock_fetch_usgs_events):
        # Arrange
        mock_fetch_usgs_events.return_value = [
            {
                "id": "1",
                "properties": {
                    "time": 123456789,
                    "mag": 4.5,
                    "place": "Location 1",
                    "url": "http://example.com/1",
                    "sources": ["source1"]
                },
                "geometry": {
                    "coordinates": [-117.1611, 34.0522, 10]
                }
            }
        ]

        producer = USGSProducer("earthquakes", "http://example.com/feed", partitioned=True)

        # Act
        producer.send_events()

        # Assert
        mock_fetch_usgs_events.assert_called_once()
        mock_normalize_event.assert_called_once()
        mock_kafka_producer.return_value.send.assert_called_once_with(
            'earthquakes',
            value=mock_normalize_event.return_value,
            key=b'NorthAmerica'
        )

    @patch('producers.usgs_producer.pd.read_csv')
    @patch('producers.usgs_producer.KafkaProducer')
    def test_send_csv_events(self, mock_kafka, mock_read_csv):

        import pandas as pd
        mock_df = pd.DataFrame({
            'latitude': [34.0, 35.0],
            'longitude': [-117.0, -118.0],
            'mag': [5.0, 6.0],
            'place': ['Place A', 'Place B'],
            'time': [123, 456]
        })
        mock_read_csv.return_value = mock_df
        
        producer = USGSProducer("test-topic", "url")

        # Act
        producer.send_csv_events("fake_path.csv", limit=2, delay=0)

        # Assert: Vérifie que Kafka a reçu les 2 messages
        self.assertEqual(producer.producer.send.call_count, 2)

    def test_geographical_zone_detection(self):
        producer = USGSProducer("test-topic", "url")
        
        event_asia = {"geometry": {"coordinates": [139.69, 35.68]}}
        key_asia = producer.get_partition_key(event_asia)
        self.assertEqual(key_asia, b'Asia')

        event_usa = {"geometry": {"coordinates": [-118.24, 34.05]}}
        key_usa = producer.get_partition_key(event_usa)
        self.assertEqual(key_usa, b'NorthAmerica')