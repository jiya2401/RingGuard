"""Deterministic attack simulator using the production graph/risk pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil
from typing import Any

import networkx as nx

from backend.graph.schema import (
    TRANSACTION_AT_MERCHANT,
    TRANSACTION_USED_DEVICE,
    TRANSACTION_USED_INSTRUMENT,
    USER_MADE_TRANSACTION,
    USER_OWNS_CARD,
    USER_PAID_MERCHANT,
    USER_SENT_TO_USER,
    USER_USED_DEVICE,
)


@dataclass(frozen=True)
class SimulationControls:
    accounts: int = 9
    shared_devices: int = 2
    shared_instruments: int = 1
    coordinated_transactions: int = 3

    def validate(self) -> "SimulationControls":
        if not 3 <= self.accounts <= 30:
            raise ValueError("accounts must be between 3 and 30")
        if not 1 <= self.shared_devices <= 5:
            raise ValueError("shared_devices must be between 1 and 5")
        if not 1 <= self.shared_instruments <= 5:
            raise ValueError("shared_instruments must be between 1 and 5")
        if not 1 <= self.coordinated_transactions <= 10:
            raise ValueError("coordinated_transactions must be between 1 and 10")
        return self


class AttackSimulator:
    def __init__(self, graph: nx.MultiDiGraph) -> None:
        self._base = graph.copy()
        self.graph = graph.copy()
        self.controls = SimulationControls()
        self.step_number = 0
        self.users: list[str] = []

    def start(self, controls: SimulationControls) -> dict[str, Any]:
        self.controls = controls.validate()
        self.graph = self._base.copy()
        self.step_number = 0
        self.users = []
        timestamp = int(self.graph.graph.get("window_end", 0)) + 60
        for index in range(self.controls.shared_devices):
            self.graph.add_node(
                f"SIM-DEV-{index + 1}",
                entity_type="DEVICE",
                created_at=timestamp,
                reason="attack simulator shared device",
            )
        for index in range(self.controls.shared_instruments):
            self.graph.add_node(
                f"SIM-CARD-{index + 1}",
                entity_type="CARD",
                created_at=timestamp,
                reason="attack simulator shared instrument",
            )
        self.graph.add_node(
            "SIM-MERCHANT-1",
            entity_type="MERCHANT",
            created_at=timestamp,
            reason="attack simulator target merchant",
        )
        return self.state()

    def step(self) -> dict[str, Any]:
        self.step_number += 1
        remaining = self.controls.accounts - len(self.users)
        add = min(remaining, max(1, ceil(self.controls.accounts / 3)))
        timestamp = int(self.graph.graph.get("window_end", 0)) + self.step_number * 3_600
        for _ in range(add):
            number = len(self.users) + 1
            user = f"SIM-U-{number:02d}"
            self.users.append(user)
            self.graph.add_node(
                user,
                entity_type="USER",
                created_at=timestamp,
                archetype="SIMULATED_ATTACK",
                reason="deterministic attack simulator account",
            )
            for device_index in range(self.controls.shared_devices):
                device = f"SIM-DEV-{device_index + 1}"
                self.graph.add_edge(
                    user,
                    device,
                    key=USER_USED_DEVICE,
                    rel_type=USER_USED_DEVICE,
                    timestamp=timestamp,
                    weight=1.0,
                )
            for card_index in range(self.controls.shared_instruments):
                card = f"SIM-CARD-{card_index + 1}"
                self.graph.add_edge(
                    user,
                    card,
                    key=USER_OWNS_CARD,
                    rel_type=USER_OWNS_CARD,
                    timestamp=timestamp,
                    weight=1.0,
                )
            for transaction_index in range(self.controls.coordinated_transactions):
                txid = f"SIM-TX-{self.step_number:02d}-{number:02d}-{transaction_index + 1:02d}"
                tx_time = timestamp + transaction_index * 20 + number
                amount = float(500 + 50 * transaction_index)
                device = f"SIM-DEV-{transaction_index % self.controls.shared_devices + 1}"
                card = f"SIM-CARD-{transaction_index % self.controls.shared_instruments + 1}"
                self.graph.add_node(
                    txid,
                    entity_type="TRANSACTION",
                    created_at=tx_time,
                    payer=user,
                    payee="SIM-MERCHANT-1",
                    amount=amount,
                    status="success",
                    reason="coordinated simulated transaction",
                )
                self._edge(user, txid, USER_MADE_TRANSACTION, tx_time, txid)
                self._edge(txid, "SIM-MERCHANT-1", TRANSACTION_AT_MERCHANT, tx_time, txid)
                self._edge(txid, card, TRANSACTION_USED_INSTRUMENT, tx_time, txid)
                self._edge(txid, device, TRANSACTION_USED_DEVICE, tx_time, txid)
                self.graph.add_edge(
                    user,
                    "SIM-MERCHANT-1",
                    key=f"{USER_PAID_MERCHANT}:{txid}",
                    rel_type=USER_PAID_MERCHANT,
                    timestamp=tx_time,
                    weight=1.0,
                    transaction_id=txid,
                )
        if len(self.users) >= 2:
            for source, target in zip(self.users[:-1], self.users[1:]):
                self.graph.add_edge(
                    source,
                    target,
                    key=f"{USER_SENT_TO_USER}:step-{self.step_number}",
                    rel_type=USER_SENT_TO_USER,
                    timestamp=timestamp + 300,
                    weight=500.0,
                )
        return self.state()

    def _edge(self, source: str, target: str, relation: str, timestamp: int, txid: str) -> None:
        self.graph.add_edge(
            source,
            target,
            key=f"{relation}:{txid}",
            rel_type=relation,
            timestamp=timestamp,
            weight=1.0,
            transaction_id=txid,
        )

    def state(self) -> dict[str, Any]:
        return {
            "step": self.step_number,
            "controls": asdict(self.controls),
            "simulated_users": list(self.users),
            "complete": len(self.users) >= self.controls.accounts,
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "data_label": "SIMULATED ATTACK / SYNTHETIC DATA",
        }
