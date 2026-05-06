import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
from producers.utils import fetch_usgs_events, normalize_event

class TestUtils(unittest.TestCase):

    @patch('producers.utils.requests.get')
    def test_fetch_usgs_events_success(self, mock_get):
        """Vérifie que la fonction retourne bien la liste 'features' du JSON"""
        # Configuration du mock
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "features": [{"id": "abc1"}, {"id": "abc2"}]
        }
        mock_get.return_value = mock_response

        # Appel
        result = fetch_usgs_events()

        # Assertions
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "abc1")
        mock_get.assert_called_once()

    @patch('producers.utils.requests.get')
    def test_fetch_usgs_events_error(self, mock_get):
        """Vérifie que raise_for_status est bien appelé en cas d'erreur HTTP"""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP Error")
        mock_get.return_value = mock_response

        with self.assertRaises(Exception):
            fetch_usgs_events()

    def test_normalize_event_structure(self):
        """Vérifie la transformation complète d'un événement brut USGS"""

        fake_event = {
            "id": "us6000",
            "properties": {
                "time": 1708441200000,
                "mag": 5.8,
                "place": "10km NE of Paris",
                "url": "http://earthquake.usgs.gov/1",
                "sources": "us,ak"
            },
            "geometry": {
                "coordinates": [2.35, 48.85, 15.5]
            }
        }

        # Appel
        normalized = normalize_event(fake_event)

        # Assertions sur les types et les valeurs
        self.assertEqual(normalized["id"], "us6000")
        self.assertEqual(normalized["magnitude"], 5.8)
        self.assertEqual(normalized["latitude"], 48.85)
        self.assertEqual(normalized["longitude"], 2.35)
        self.assertEqual(normalized["depth"], 15.5)
        

        self.assertIn("2024-02-20T15:00:00", normalized["time"])

        self.assertEqual(normalized["source"], "us,ak")

    def test_normalize_event_default_source(self):
        """Vérifie que la source par défaut est 'usgs' si absente"""
        fake_event = {
            "id": "test_id",
            "properties": {
                "time": 0, "mag": 1.0, "place": "X", "url": "Y"
                # Pas de champ 'sources' ici
            },
            "geometry": {"coordinates": [0, 0, 0]}
        }
        normalized = normalize_event(fake_event)
        self.assertEqual(normalized["source"], "usgs")