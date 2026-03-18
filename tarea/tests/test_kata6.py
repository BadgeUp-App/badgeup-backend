import io
import json
from pathlib import Path
import unittest

from tarea.kata6.bank import Account, StatementPrinter, TransactionRepository


DATA_FILE = Path(__file__).parent / "data" / "kata6_cases.json"


class FakeClock:
    def __init__(self, dates):
        self._dates = iter(dates)

    def today(self):
        try:
            return next(self._dates)
        except StopIteration as exc:  # pragma: no cover - defensive
            raise AssertionError("Clock exhausted more dates than expected") from exc


class Kata6BankingTests(unittest.TestCase):
    def test_statement_scenarios(self):
        with DATA_FILE.open(encoding="utf-8") as handle:
            cases = json.load(handle)

        for case in cases:
            dates = [operation["date"] for operation in case["operations"]]
            clock = FakeClock(dates)
            repository = TransactionRepository(clock)
            output = io.StringIO()
            printer = StatementPrinter(output)
            account = Account(repository, printer)

            with self.subTest(case=case["name"]):
                for operation in case["operations"]:
                    action = operation["action"]
                    amount = operation["amount"]
                    getattr(account, action)(amount)

                account.printStatement()
                statement = output.getvalue().strip().splitlines()
                self.assertEqual(case["expected_statement"], statement)


if __name__ == "__main__":
    unittest.main()
