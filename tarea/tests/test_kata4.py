import json
from pathlib import Path
import unittest

from tarea.kata4.search import search_cities


DATA_FILE = Path(__file__).parent / "data" / "kata4_cases.json"


class Kata4SearchTests(unittest.TestCase):
    def test_search_cases(self):
        with DATA_FILE.open(encoding="utf-8") as handle:
            cases = json.load(handle)

        for case in cases:
            with self.subTest(case=case["name"]):
                result = search_cities(case["query"])
                self.assertEqual(case["expected"], result)


if __name__ == "__main__":
    unittest.main()
