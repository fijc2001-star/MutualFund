"""Backtest (M8, minimal) — run a bot over its full history through the SAME live pipeline.

Reuses the engine (M9), sizing + risk + guardrails (M6), the sandbox venue (M5) and the
performance calculator (M10) so a backtest can't diverge from live behaviour. Produces a
performance summary + equity curve; nothing is persisted (the run is rolled back).
"""
