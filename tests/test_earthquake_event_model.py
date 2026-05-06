import unittest
from pydantic import ValidationError
from models.earthquake import EarthquakeEvent

class TestEarthquakeEventModel(unittest.TestCase):

    def test_valid_event_creation(self):
        # Arrange
        data_test = {
            "id": "1",
            "time": "2024-01-01T12:00:00Z",
            "latitude": 34.05,
            "longitude": -117.16,
            "depth": 10.0,
            "magnitude": 4.5,
            "place": "LA",
            "status": "reviewed",
            "url": "http://test.com/test"
        }

        # Act
        event = EarthquakeEvent(**data_test)

        # Assert
        self.assertEqual(event.id, "1")
        self.assertEqual(event.time, "2024-01-01T12:00:00Z")
        self.assertEqual(event.latitude, 34.05)
        self.assertEqual(event.longitude, -117.16)
        self.assertEqual(event.depth, 10.0)
        self.assertEqual(event.magnitude, 4.5)
        self.assertEqual(event.place, "LA")
        self.assertEqual(event.status, "reviewed")
        self.assertEqual(event.url, "http://test.com/test")

    def test_missing_required_field(self):
        # Arrange
        payload = {
            # id manquant
            "time": "2024-01-01T12:00:00Z",
            "latitude": 34.05,
            "longitude": -117.16,
            "depth": 10.0,
            "magnitude": 4.5,
            "place": "LA",
            "status": "reviewed",
            "url": "http://test.com/test"
        }

        # Act + Assert
        with self.assertRaises(TypeError):
            EarthquakeEvent(**payload)

    def test_default_source_value(self):
        # Arrange : on ne fournit PAS "source"
        payload = {
            "id": "1",
            "time": "2024-01-01T12:00:00Z",
            "latitude": 40.0,
            "longitude": -120.5,
            "depth": 5.0,
            "magnitude": 3.2,
            "place": "California",
            "status": "reviewed",
            "url": "http://test.com"
        }

        # Act
        event = EarthquakeEvent(**payload)

        # Assert
        self.assertEqual(event.source, "usgs")