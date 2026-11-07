"""Convert agent events into RingGuard's existing Ecosystem (new work).

Mapping (a deliberate shortcut so the existing pipeline can be reused):
  agent            -> USER
  shared resource  -> DEVICE   (USER_USED_DEVICE edges = "touched the same thing")
  agent->agent msg -> Payment with payee_type="user"   (USER_SENT_TO_USER edge)
"""

from __future__ import annotations

from backend.data.model import (
    CARD,
    DEVICE,
    IP,
    PAYEE_USER,
    TRANSACTION,
    USER,
    Ecosystem,
    Entity,
    Payment,
)
from backend.swarm.schema import MESSAGE, USE_RESOURCE, AgentEvent


def events_to_ecosystem(events: list[AgentEvent], seed: int = 0) -> Ecosystem:
    t0 = min((e.ts for e in events), default=0)
    agents = sorted({e.agent for e in events} | {e.target for e in events if e.kind == MESSAGE})
    resources = sorted({e.target for e in events if e.kind == USE_RESOURCE})

    uses: dict[str, set[str]] = {a: set() for a in agents}
    for e in events:
        if e.kind == USE_RESOURCE:
            uses[e.agent].add(e.target)

    users = [
        Entity(a, USER, t0, attributes={"devices": sorted(uses[a])}, reason="agent")
        for a in agents
    ]
    devices = [Entity(r, DEVICE, t0, reason="shared resource") for r in resources]

    payments = []
    cards, ips, txns = [], [], []
    for e in events:
        if e.kind == MESSAGE:
            # Unique placeholder nodes so the payment-shaped graph builder stays
            # happy without creating false links between agents.
            cards.append(Entity(f"x-instr-{e.event_id}", CARD, e.ts, reason="placeholder"))
            ips.append(Entity(f"x-ip-{e.event_id}", IP, e.ts, reason="placeholder"))
            devices.append(Entity(f"x-dev-{e.event_id}", DEVICE, e.ts, reason="placeholder"))
            txns.append(Entity(f"msg-{e.event_id}", TRANSACTION, e.ts, reason="agent message"))
            payments.append(
                Payment(
                    transaction_id=f"msg-{e.event_id}",
                    payer=e.agent,
                    payee_type=PAYEE_USER,
                    payee=e.target,
                    amount=1.0,
                    instrument_type="CARD",
                    instrument=f"x-instr-{e.event_id}",
                    ip_id=f"x-ip-{e.event_id}",
                    device_id=f"x-dev-{e.event_id}",
                    timestamp=e.ts,
                    reason="agent message",
                )
            )
    return Ecosystem(
        seed=seed,
        entities={USER: users, DEVICE: devices, CARD: cards, IP: ips, TRANSACTION: txns},
        payments=payments,
        profile={"window_start": t0, "window_end": max((e.ts for e in events), default=t0)},
    ) 