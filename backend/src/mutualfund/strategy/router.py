"""Bot & strategy REST API (M3 over HTTP).

Designers create/publish bots and move them through their lifecycle; the strategy catalog
(with param schemas) drives the designer UI. All routes are authenticated; mutations require
the Designer role. Tenancy is enforced by the principal dependency (sets TenantContext).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ValidationError

from ..foundation.uow import UnitOfWork
from ..iam.deps import CurrentPrincipal, require_role
from ..iam.roles import Principal, Role
from ..lifecycle.lifecycle import BotLifecycle, BotState, IllegalTransitionError
from .models import Bot, BotRegistry, BotVersion
from .registry import UnknownStrategyError, default_registry

router = APIRouter(tags=["bots"])

DesignerPrincipal = Annotated[Principal, Depends(require_role(Role.DESIGNER))]


# --- DTOs ---

class StrategyInfo(BaseModel):
    id: str
    params_schema: dict[str, Any]


class BotVersionInfo(BaseModel):
    id: str
    version: int
    strategy_id: str
    params: dict[str, Any]
    universe: list[str]
    state: str
    qualified_policy: str | None
    qualified_policy_version: int | None
    created_at: datetime


class BotSummary(BaseModel):
    id: str
    name: str
    state: str
    current_version: int
    created_at: datetime


class BotDetail(BotSummary):
    versions: list[BotVersionInfo]


class CreateBotRequest(BaseModel):
    name: str
    strategy_id: str
    params: dict[str, Any] = {}
    universe: list[str] = []


class PublishRequest(BaseModel):
    strategy_id: str
    params: dict[str, Any] = {}
    universe: list[str] = []


class TransitionRequest(BaseModel):
    to: str
    reason: str = ""


def _version_info(v: BotVersion) -> BotVersionInfo:
    return BotVersionInfo(
        id=v.id,
        version=v.version,
        strategy_id=v.strategy_id,
        params=dict(v.params),
        universe=list(v.universe),
        state=v.state,
        qualified_policy=v.qualified_policy,
        qualified_policy_version=v.qualified_policy_version,
        created_at=v.created_at,
    )


def _summary(b: Bot) -> BotSummary:
    return BotSummary(
        id=b.id,
        name=b.name,
        state=b.state,
        current_version=b.current_version,
        created_at=b.created_at,
    )


def _detail(b: Bot, versions: list[BotVersion]) -> BotDetail:
    return BotDetail(**_summary(b).model_dump(), versions=[_version_info(v) for v in versions])


def _publish_or_400(exc: Exception) -> HTTPException:
    if isinstance(exc, UnknownStrategyError):
        return HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown strategy: {exc}")
    if isinstance(exc, ValidationError):
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()],
        )
    raise exc


# --- routes ---

@router.get("/strategies", response_model=list[StrategyInfo])
async def list_strategies(_: CurrentPrincipal) -> list[StrategyInfo]:
    out: list[StrategyInfo] = []
    for sid in default_registry.ids():
        schema = default_registry.get(sid).params_model.model_json_schema()
        out.append(StrategyInfo(id=sid, params_schema=schema))
    return out


@router.get("/bots", response_model=list[BotSummary])
async def list_bots(principal: CurrentPrincipal) -> list[BotSummary]:
    async with UnitOfWork() as uow:
        bots = await BotRegistry(uow.session).list_bots(principal.user_id)
    return [_summary(b) for b in bots]


@router.post("/bots", response_model=BotDetail, status_code=status.HTTP_201_CREATED)
async def create_bot(body: CreateBotRequest, principal: DesignerPrincipal) -> BotDetail:
    async with UnitOfWork() as uow:
        registry = BotRegistry(uow.session)
        bot = await registry.create_bot(name=body.name, owner_id=principal.user_id)
        try:
            await registry.publish(
                bot, strategy_id=body.strategy_id, params=body.params, universe=body.universe
            )
        except (UnknownStrategyError, ValidationError) as exc:
            raise _publish_or_400(exc) from exc
        versions = await registry.versions(bot.id)
        await uow.commit()
    return _detail(bot, versions)


@router.get("/bots/{bot_id}", response_model=BotDetail)
async def get_bot(bot_id: str, principal: CurrentPrincipal) -> BotDetail:
    async with UnitOfWork() as uow:
        registry = BotRegistry(uow.session)
        bot = await registry.get_bot(bot_id)
        if bot is None or bot.owner_id != principal.user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot not found")
        versions = await registry.versions(bot_id)
    return _detail(bot, versions)


@router.post("/bots/{bot_id}/versions", response_model=BotVersionInfo)
async def publish_version(
    bot_id: str, body: PublishRequest, principal: DesignerPrincipal
) -> BotVersionInfo:
    async with UnitOfWork() as uow:
        registry = BotRegistry(uow.session)
        bot = await registry.get_bot(bot_id)
        if bot is None or bot.owner_id != principal.user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot not found")
        try:
            version = await registry.publish(
                bot, strategy_id=body.strategy_id, params=body.params, universe=body.universe
            )
        except (UnknownStrategyError, ValidationError) as exc:
            raise _publish_or_400(exc) from exc
        await uow.commit()
    return _version_info(version)


@router.post("/bots/{bot_id}/transition", response_model=BotVersionInfo)
async def transition_bot(
    bot_id: str, body: TransitionRequest, principal: DesignerPrincipal
) -> BotVersionInfo:
    try:
        to = BotState(body.to)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown state: {body.to}") from exc

    async with UnitOfWork() as uow:
        registry = BotRegistry(uow.session)
        bot = await registry.get_bot(bot_id)
        if bot is None or bot.owner_id != principal.user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Bot not found")
        versions = await registry.versions(bot_id)
        current = next((v for v in versions if v.version == bot.current_version), None)
        if current is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bot has no published version")
        try:
            await BotLifecycle(uow.session).transition(
                current, to, reason=body.reason or "manual", actor=principal.user_id
            )
        except IllegalTransitionError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        bot.state = current.state  # mirror lifecycle state onto the bot for listing
        await uow.commit()
    return _version_info(current)
