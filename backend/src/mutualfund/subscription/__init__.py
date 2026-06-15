"""Subscriptions (M11, minimal) — a thin pointer into a bot's persisted signal stream.

A subscription does NOT copy the bot's signals; the signal stream belongs to the bot and is
persisted once (hash-chained SIGNAL events on the EventLedger). A subscription just records
which bot + when the user joined (`started_at`), so "replay since I subscribed" is a windowed
read of the shared stream. Per-subscriber execution (own account/fills) is out of scope here.
"""

from . import models  # noqa: F401  (register tables on Base.metadata)
