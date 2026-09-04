"""Heterogeneous payment-ecosystem graph schema.

Single source of truth for node/relationship type constants and edge
attribute keys. Kept independent of NetworkX so the schema survives a
migration to Neo4j (spec §3, §45).
"""

from __future__ import annotations

from backend.data.model import (
    ADDRESS,
    BANK_ACCOUNT,
    CARD,
    DEVICE,
    IP,
    MANDATE,
    MERCHANT,
    PHONE,
    SESSION,
    TRANSACTION,
    UPI_ID,
    USER,
)

# Relationship types (spec §3)
USER_OWNS_CARD = "USER_OWNS_CARD"
USER_OWNS_BANK_ACCOUNT = "USER_OWNS_BANK_ACCOUNT"
USER_USED_UPI_ID = "USER_USED_UPI_ID"
USER_HAS_PHONE = "USER_HAS_PHONE"
USER_LIVES_AT_ADDRESS = "USER_LIVES_AT_ADDRESS"
USER_USED_DEVICE = "USER_USED_DEVICE"
USER_USED_IP = "USER_USED_IP"
USER_HAS_MANDATE = "USER_HAS_MANDATE"
USER_CREATED_SESSION = "USER_CREATED_SESSION"
SESSION_USED_DEVICE = "SESSION_USED_DEVICE"
SESSION_USED_IP = "SESSION_USED_IP"
USER_MADE_TRANSACTION = "USER_MADE_TRANSACTION"
TRANSACTION_AT_MERCHANT = "TRANSACTION_AT_MERCHANT"
TRANSACTION_USED_INSTRUMENT = "TRANSACTION_USED_INSTRUMENT"
TRANSACTION_USED_IP = "TRANSACTION_USED_IP"
TRANSACTION_USED_DEVICE = "TRANSACTION_USED_DEVICE"
USER_SENT_TO_USER = "USER_SENT_TO_USER"
USER_PAID_MERCHANT = "USER_PAID_MERCHANT"

# Edges that can carry money-flow semantics (used by the risk engine).
MONEY_FLOW_RELS = frozenset({USER_SENT_TO_USER, USER_PAID_MERCHANT})

# Instrument relation lookups validated by the builder.
INSTRUMENT_REL = {
    CARD: USER_OWNS_CARD,
    BANK_ACCOUNT: USER_OWNS_BANK_ACCOUNT,
    UPI_ID: USER_USED_UPI_ID,
}

# Standard edge attribute keys.
ATTR_REL_TYPE = "rel_type"
ATTR_TIMESTAMP = "timestamp"
ATTR_WEIGHT = "weight"
ATTR_TXN_ID = "transaction_id"
ATTR_METADATA = "metadata"

REQUIRED_EDGE_ATTRS = frozenset({ATTR_REL_TYPE, ATTR_TIMESTAMP, ATTR_WEIGHT})