"""
Kata 6 – Banking kata.

Implements an Account class that records transactions and prints statements.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Protocol


@dataclass(frozen=True)
class Transaction:
    date: str
    amount: int


class Clock(Protocol):
    def today(self) -> str:
        """Return today's date as a string in dd/mm/yyyy format."""


class SystemClock:
    def today(self) -> str:
        return datetime.now().strftime("%d/%m/%Y")


class TransactionRepository:
    def __init__(self, clock: Clock):
        self._clock = clock
        self._transactions: List[Transaction] = []

    def add_transaction(self, amount: int) -> None:
        self._transactions.append(Transaction(self._clock.today(), amount))

    def all_transactions(self) -> List[Transaction]:
        return list(self._transactions)


class StatementPrinter:
    HEADER = "DATE       | AMOUNT  | BALANCE"

    def __init__(self, output):
        self._output = output

    def print(self, transactions: Iterable[Transaction]) -> None:
        self._output.write(self.HEADER + "\n")
        running_balance = 0
        lines: List[str] = []
        for transaction in transactions:
            running_balance += transaction.amount
            amount_str = self._format_amount(transaction.amount)
            balance_str = self._format_amount(running_balance)
            lines.append(f"{transaction.date} | {amount_str} | {balance_str}")

        for line in reversed(lines):
            self._output.write(line + "\n")

    @staticmethod
    def _format_amount(amount: int) -> str:
        return f"{amount:.2f}"


class Account:
    def __init__(self, repository: TransactionRepository, printer: StatementPrinter):
        self._repository = repository
        self._printer = printer

    def deposit(self, amount: int) -> None:
        self._repository.add_transaction(abs(amount))

    def withdraw(self, amount: int) -> None:
        self._repository.add_transaction(-abs(amount))

    def printStatement(self) -> None:  # noqa: N802 - kata signature requirement
        self._printer.print(self._repository.all_transactions())
