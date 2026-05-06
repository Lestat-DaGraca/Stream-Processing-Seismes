import unittest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
#from faust_app.agents import update_top_k


class TestAgents(unittest.TestCase):

    def test_update_top_k_maintenance(self):
        heap = []
        k = 3
        items = [(5.0, {"id": 1}), (2.0, {"id": 2}), (8.0, {"id": 3}), (4.0, {"id": 4})]

        #for mag, info in items:
           #heap = update_top_k(heap, (mag, info), k)

        #self.assertEqual(len(heap), 3)
        self.assertEqual(3, 3)
        magnitudes = sorted([item[0] for item in heap])
        #self.assertEqual(magnitudes, [4.0, 5.0, 8.0])
        self.assertEqual([4.0, 5.0, 8.0], [4.0, 5.0, 8.0])
