"""Agentic strategy: a Claude-driven decision-maker that confirms or vetoes trade candidates.

A cheap, deterministic SMA cross proposes *candidate* entries/exits; at each candidate the
strategy consults an `LLMClient` to decide whether to act (BUY/SELL) or stand down (hold),
attaching the agent's reasoning as the signal `Rationale`. Consulting only at candidates keeps
LLM calls bounded (tens over a full backtest, not one per bar).

The client is pluggable: a real Claude (`AnthropicLLMClient`) when `ANTHROPIC_API_KEY` is set, a
deterministic `StubLLMClient` otherwise — so the strategy registers, backtests, qualifies, and
slots into a portfolio today, and goes live with a key (no other code changes). Because the engine
rebuilds the strategy each tick, the client is a memoized singleton (`make_llm_client`).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field, model_validator

from ...config import get_settings
from ...signals.signal import Action, Rationale, Signal
from ..strategy import RegisteredStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)

_RECENT_CLOSES = 12  # how many recent closes to summarize for the agent


class AgentParams(BaseModel):
    """Candidate-trigger windows + the RSI context window the agent reasons over."""

    fast: int = Field(default=9, gt=0)
    slow: int = Field(default=21, gt=0)
    rsi_len: int = Field(default=14, gt=1)
    style: str = Field(default="balanced", min_length=1, max_length=40)

    @model_validator(mode="after")
    def _fast_below_slow(self) -> AgentParams:
        if self.fast >= self.slow:
            raise ValueError("fast window must be shorter than slow window")
        return self


@dataclass(frozen=True, slots=True)
class AgentView:
    """The compact market snapshot handed to the agent at a candidate moment."""

    symbol: str
    candidate: str  # "buy" | "sell" — the proposed action to confirm or veto
    fast: float
    slow: float
    rsi: float | None
    recent_closes: tuple[float, ...]
    position: float
    style: str


@dataclass(frozen=True, slots=True)
class AgentDecision:
    """The agent's verdict on a candidate: act (matching side) or hold, plus its reasoning."""

    action: str  # "buy" | "sell" | "hold"
    thesis: str
    invalidation: str | None = None


@runtime_checkable
class LLMClient(Protocol):
    """Turns a market view into a trade decision. Sync, so it slots into the sync engine."""

    def decide(self, view: AgentView) -> AgentDecision: ...


def _rsi_text(rsi: float | None) -> str:
    return f"{rsi:.0f}" if rsi is not None else "n/a"


class StubLLMClient:
    """Deterministic stand-in for Claude: confirms the candidate unless RSI argues against it.

    Buys are vetoed when momentum is already overbought (RSI ≥ 70), sells when oversold (≤ 30) —
    a small, explainable discipline so behavior is sensible and *reproducible* with no API key.
    """

    def decide(self, view: AgentView) -> AgentDecision:
        rsi = view.rsi
        rsi_txt = _rsi_text(rsi)
        if view.candidate == "buy":
            if rsi is not None and rsi >= 70:
                return AgentDecision(
                    "hold",
                    thesis=f"Trend turned up but RSI {rsi_txt} is overbought — waiting for a dip.",
                )
            return AgentDecision(
                "buy",
                thesis=(
                    f"Trend flipped up (SMA fast {view.fast:.2f} > slow {view.slow:.2f}) with RSI "
                    f"{rsi_txt} supportive — entering long."
                ),
                invalidation="trend rolls back below the slow average or RSI breaks down",
            )
        if rsi is not None and rsi <= 30:
            return AgentDecision(
                "hold",
                thesis=f"Trend turned down but RSI {rsi_txt} is oversold — holding the dip.",
            )
        return AgentDecision(
            "sell",
            thesis=(
                f"Trend flipped down (SMA fast {view.fast:.2f} < slow {view.slow:.2f}) with RSI "
                f"{rsi_txt} — exiting the long."
            ),
            invalidation="trend reclaims the slow average",
        )


_SYSTEM = (
    "You are a disciplined systematic trading agent. A mechanical SMA-cross model has proposed a "
    "candidate trade; your job is to confirm it (act) or veto it (hold) using the supplied market "
    "context. You never invent a trade the model did not propose. Respond ONLY in the requested "
    "JSON. 'action' must be the proposed side to act, or 'hold' to stand down. Keep 'thesis' to "
    "one or two sentences a trader could read on a chart."
)

_DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["buy", "sell", "hold"]},
        "thesis": {"type": "string"},
        "invalidation": {"type": ["string", "null"]},
    },
    "required": ["action", "thesis", "invalidation"],
    "additionalProperties": False,
}


def _prompt(view: AgentView) -> str:
    closes = ", ".join(f"{c:.2f}" for c in view.recent_closes)
    return (
        f"Symbol: {view.symbol}\n"
        f"Trading style: {view.style}\n"
        f"Proposed action: {view.candidate}\n"
        f"Fast SMA: {view.fast:.2f}  Slow SMA: {view.slow:.2f}\n"
        f"RSI: {_rsi_text(view.rsi)}\n"
        f"Current position: {view.position:g}\n"
        f"Recent closes (old→new): {closes}\n\n"
        "Confirm or veto the proposed action."
    )


class AnthropicLLMClient:
    """Claude-backed decision-maker. Falls back to the stub's verdict on any API/parse error, so a

    transient failure or a misconfigured key never crashes a backtest or a live tick.
    """

    def __init__(self, *, api_key: str, model: str) -> None:
        import anthropic  # type: ignore[import-not-found]  # optional dep; only when a key is set

        self._client: Any = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._fallback = StubLLMClient()

    def decide(self, view: AgentView) -> AgentDecision:
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                thinking={"type": "adaptive"},
                system=_SYSTEM,
                messages=[{"role": "user", "content": _prompt(view)}],
                output_config={"format": {"type": "json_schema", "schema": _DECISION_SCHEMA}},
            )
            text = next(b.text for b in resp.content if b.type == "text")
            data = json.loads(text)
            action = data.get("action", "hold")
            if action not in ("buy", "sell", "hold"):
                action = "hold"
            invalidation = data.get("invalidation")
            return AgentDecision(
                action,
                thesis=str(data.get("thesis", "")),
                invalidation=str(invalidation) if invalidation else None,
            )
        except Exception:  # pragma: no cover - network/parse failure path
            logger.warning("Agent LLM call failed; using deterministic fallback.", exc_info=True)
            return self._fallback.decide(view)


_client_singleton: LLMClient | None = None


def make_llm_client() -> LLMClient:
    """Process-wide singleton: real Claude when a key is set, the deterministic stub otherwise."""
    global _client_singleton
    if _client_singleton is None:
        settings = get_settings()
        key = settings.anthropic_api_key
        if key:
            try:
                _client_singleton = AnthropicLLMClient(api_key=key, model=settings.agent_model)
            except Exception:  # missing SDK / bad init → stay functional with the stub
                logger.warning(
                    "Anthropic SDK unavailable; agent strategy using deterministic stub."
                )
                _client_singleton = StubLLMClient()
        else:
            _client_singleton = StubLLMClient()
    return _client_singleton


def _rsi(closes: Sequence[float], length: int) -> float | None:
    """Average-gain/loss RSI over the last `length` deltas; None until there are enough closes."""
    if length <= 0 or len(closes) < length + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(len(closes) - length, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains += diff
        else:
            losses -= diff
    avg_loss = losses / length
    if avg_loss == 0:
        return 100.0
    rs = (gains / length) / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


class AgentStrategy(RegisteredStrategy):
    strategy_id = "agent"
    params_model = AgentParams

    def __init__(self, fast: int, slow: int, rsi_len: int, style: str, client: LLMClient) -> None:
        self._fast = fast
        self._slow = slow
        self._rsi_len = rsi_len
        self._style = style
        self._client = client

    @classmethod
    def build(cls, params: BaseModel) -> Strategy:
        assert isinstance(params, AgentParams)
        return cls(params.fast, params.slow, params.rsi_len, params.style, make_llm_client())

    def evaluate(self, ctx: StrategyContext) -> list[Signal]:
        fast = ctx.sma(self._fast)
        slow = ctx.sma(self._slow)
        prev_fast = ctx.sma(self._fast, offset=1)
        prev_slow = ctx.sma(self._slow, offset=1)
        if fast is None or slow is None or prev_fast is None or prev_slow is None:
            return []

        crossed_up = prev_fast <= prev_slow and fast > slow
        crossed_down = prev_fast >= prev_slow and fast < slow
        if crossed_up and ctx.position <= 0:
            candidate = "buy"
        elif crossed_down and ctx.position > 0:
            candidate = "sell"
        else:
            return []

        rsi = _rsi(ctx.closes, self._rsi_len)
        view = AgentView(
            symbol=ctx.instrument.symbol,
            candidate=candidate,
            fast=fast,
            slow=slow,
            rsi=rsi,
            recent_closes=tuple(ctx.closes[-_RECENT_CLOSES:]),
            position=float(ctx.position),
            style=self._style,
        )
        decision = self._client.decide(view)
        if decision.action != candidate:  # agent vetoed the candidate
            return []

        action = Action.BUY if candidate == "buy" else Action.SELL
        indicators = [
            f"SMA({self._fast})={fast:.4f}",
            f"SMA({self._slow})={slow:.4f}",
            f"RSI({self._rsi_len})={_rsi_text(rsi)}",
        ]
        return [
            Signal(
                ctx.instrument,
                action,
                Decimal(1),
                Rationale(
                    thesis=decision.thesis,
                    indicators=indicators,
                    invalidation=decision.invalidation,
                ),
            )
        ]
