"""Module M10 — Performance & Ledger (ARCHITECTURE §3.7, REQUIREMENTS §5.8.1).

Append-only, hash-chained event ledger; performance derived by replaying it.
"""

from . import models  # noqa: F401  (register tables on Base.metadata)
