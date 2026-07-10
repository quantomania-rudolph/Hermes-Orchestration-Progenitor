"""T29 — Phase-Transition Controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from tools.common import ContractViolation, Phase


@dataclass
class TransitionContract:
    name: str
    check_entry: Callable[[dict], None]
    assert_exit: Callable[[dict], None]


class PhaseTransitionController:
    def __init__(self) -> None:
        self.contracts: dict[str, TransitionContract] = {}
        self._dirty_from: str | None = None

    def register(self, contract: TransitionContract) -> None:
        self.contracts[contract.name] = contract

    def transition(self, state: dict, from_phase: Phase, to_phase: Phase) -> None:
        exit_name = f"{from_phase.value}_to_{to_phase.value}"
        entry_name = exit_name
        contract = self.contracts.get(entry_name)
        if contract is None:
            raise ContractViolation(f"No contract registered for {exit_name}")
        contract.check_entry(state)
        self._dirty_from = from_phase.value

    def assert_exit(self, state: dict, from_phase: Phase, to_phase: Phase) -> None:
        name = f"{from_phase.value}_to_{to_phase.value}"
        contract = self.contracts.get(name)
        if contract is None:
            raise ContractViolation(f"No exit contract for {name}")
        contract.assert_exit(state)
        self._dirty_from = None

    def has_dirty_contract(self) -> bool:
        return self._dirty_from is not None
