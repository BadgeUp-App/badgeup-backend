import json
from pathlib import Path
import unittest

from tarea.kata5.pos import PointOfSaleTerminal


DATA_FILE = Path(__file__).parent / "data" / "kata5_cases.json"


class Kata5PointOfSaleTests(unittest.TestCase):
    def test_process_commands(self):
        with DATA_FILE.open(encoding="utf-8") as handle:
            cases = json.load(handle)

        for case in cases:
            terminal = PointOfSaleTerminal()
            with self.subTest(case=case["name"]):
                for step in case["steps"]:
                    response = terminal.process(step["input"])
                    self.assertEqual(step["expected"], response)


if __name__ == "__main__":
    unittest.main()
