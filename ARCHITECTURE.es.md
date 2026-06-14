# MutualFund — Arquitectura: Módulos e Interfaces

> 🌐 Traducción al español de [`ARCHITECTURE.md`](./ARCHITECTURE.md). En caso de discrepancia, **la versión en inglés es la fuente de verdad**. Los identificadores de código (nombres de interfaces, tipos) se mantienen en inglés.

> Complemento de [`REQUIREMENTS.es.md`](./REQUIREMENTS.es.md). Define los **módulos principales** (contextos delimitados) del backend de Python/FastAPI y las **interfaces centrales** que los desacoplan. Objetivo: empezar a construir contra contratos estables.
>
> Regla guía (§4): **el LLM razona; el código determinista decide los números.** Los módulos cuant/de dinero exponen interfaces simples y testeables; el agente solo las *invoca*.

---

## 1. Vista por capas

```
┌──────────────────────────────────────────────────────────────────┐
│  CAPA DE INTERFAZ  API Gateway (REST + WebSocket, OpenAPI) · BFF   │
├──────────────────────────────────────────────────────────────────┤
│  INTELIGENCIA      Agente/Copiloto (orquestación LLM) · Señales    │
├──────────────────────────────────────────────────────────────────┤
│  PLATAFORMA/NEGOCIO Identidad y Acceso · Mercado · Suscripciones   │
│                    y Facturación · Admin/Config · Notificaciones   │
├──────────────────────────────────────────────────────────────────┤
│  DOMINIO DE TRADING Bot/Estrategia · Ciclo de vida y Calificación ·│
│                    Datos de Mercado · Ejecución/Sandbox · Riesgo · │
│                    Portafolio · Backtesting · Rendimiento y Ledger │
├──────────────────────────────────────────────────────────────────┤
│  FUNDAMENTO        Modelo Instrument · Persistencia · Multi-inquil.│
│                    · Auditoría · Config  (transversal)             │
└──────────────────────────────────────────────────────────────────┘
```

**Regla de dependencia:** las capas superiores dependen de las inferiores, nunca al revés. El Dominio de Trading no sabe nada de HTTP, facturación ni del LLM. El Agente orquesta los módulos de dominio a través de sus interfaces pero no contiene lógica cuant/de dinero.

---

## 2. Mapa de módulos

| # | Módulo | Responsabilidad | Interfaces clave que posee | Depende de |
|---|--------|-----------------|----------------------------|------------|
| M1 | **Identidad y Acceso (IAM)** | Login OAuth/OIDC (Authlib), sesiones/JWT, usuarios, roles RBAC, multi-inquilino, root admin | `IdentityProvider`, `SessionManager`, `RoleService`, `TenantContext` | Fundamento |
| M2 | **Datos de Mercado** | Cotizaciones/barras/cadenas de opciones; catálogo `Instrument` | `MarketDataProvider`, `InstrumentCatalog` | Fundamento |
| M3 | **Bot y Estrategia** | Bloques de estrategia; definición del bot, parámetros, **versionado inmutable** | `Strategy`, `BotRegistry`, `BotVersion` | M2 |
| M4 | **Ciclo de vida y Calificación** | Máquina de estados del bot; política de calificación enchufable | `BotLifecycle`, `QualificationCriterion`, `QualificationPolicy` | M3, M10 |
| M5 | **Ejecución / Sandbox** | `ExecutionVenue` (sandbox ahora, bróker después); sandbox por suscripción; modelos de ejecución enchufables | `ExecutionVenue`, `SandboxLedger`, `BrokerAdapter`, `FillPriceModel`, `SlippageModel`, `CommissionModel`, `OptionsPricingModel` | M2 |
| M6 | **Riesgo y Dimensionamiento** | Límites por operación/portafolio, sizing por volatilidad, barreras estrictas | `RiskModel`, `PositionSizer`, `GuardrailPolicy` | M2 |
| M7 | **Construcción de Portafolio** | Optimizador con restricciones de riesgo | `PortfolioOptimizer` | M6 |
| M8 | **Backtesting** | Motor respaldado por framework OSS que comparte el camino de código en vivo | `BacktestEngine`, `DataFeed` | M2, M3, M5, M6 |
| M9 | **Señales** | Correr bots → producir flujos de señales clasificadas y explicadas | `SignalEngine`, `SignalStream`, `Signal` | M3, M5, M6 |
| M10 | **Rendimiento y Ledger** | Ledger solo-anexar y **encadenado por hash**; métricas de rendimiento; verificación | `EventLedger`, `PerformanceCalculator`, `PerformanceRecord` | Fundamento |
| M11 | **Suscripciones y Facturación** | Suscripciones, Stripe Connect, pagos, reparto de comisión, dunning, ciclo de vida | `BillingProvider`, `SubscriptionService`, `PayoutService` | M1 |
| M12 | **Mercado** | Catálogo, descubrimiento, búsqueda/ranking, detalle del bot | `MarketplaceService`, `BotQuery` | M3, M4, M10, M11 |
| M13 | **Agente / Copiloto** | Orquestación LLM; explica señales; narrativas; invoca herramientas de dominio | `AgentOrchestrator`, `AgentTool`, `LLMClient` | M2,M6,M9,M10 (mayormente lectura) |
| M14 | **Admin / Config** | Config global (% comisión, prima, umbrales, límites de tarifa), moderación, kill-switch | `ConfigStore`, `ModerationService`, `KillSwitch` | M1 |
| M15 | **Notificaciones** | Alertas de nuevas señales/ejecuciones | `NotificationChannel`, `Notifier` | M9, M11 |
| M16 | **API Gateway / BFF** | Endpoints REST + WebSocket, middleware de auth, OpenAPI, mapeo de DTOs | (routers HTTP, hubs WS) | todos los anteriores |
| X | **Fundamento** (transversal) | Modelo `Instrument`, persistencia/UoW, `TenantContext`, `AuditLog`, `Clock` | `Repository`, `UnitOfWork`, `AuditLog`, `Clock` | — |

---

## 3. Interfaces centrales del dominio (bosquejos de protocolos en Python)

> Firmas ilustrativas para anclar los contratos — los nombres/formas se afinarán en el código. Usar `typing.Protocol` o ABCs. Todos los tipos de dinero/cuant usan `Decimal`, nunca float.

### 3.1 Fundamento — Instrument y transversales

```python
class AssetClass(str, Enum):
    EQUITY = "equity"; OPTION = "option"  # FUTURE, CRYPTO, FX después

@dataclass(frozen=True)
class Instrument:
    symbol: str
    asset_class: AssetClass
    multiplier: Decimal = Decimal(1)        # multiplicador de contrato opciones/futuros
    expiry: date | None = None              # opciones/futuros
    strike: Decimal | None = None           # opciones
    option_type: Literal["C", "P"] | None = None
    tick_size: Decimal = Decimal("0.01")

class Clock(Protocol):
    def now(self) -> datetime: ...          # inyectable para backtests/sandbox

class AuditLog(Protocol):
    def record(self, event_type: str, actor: ActorRef, payload: dict) -> None: ...

class TenantContext(Protocol):
    @property
    def tenant_id(self) -> TenantId: ...     # aplicado en cada consulta del repositorio
```

### 3.2 M2 — Datos de Mercado

```python
class MarketDataProvider(Protocol):                  # primera impl: ThinkorSwim/Schwab
    def quote(self, ins: Instrument) -> Quote: ...
    def bars(self, ins: Instrument, tf: TimeFrame, start, end) -> list[Bar]: ...
    def option_chain(self, underlying: str, expiry: date | None) -> OptionChain: ...
    def stream(self, instruments: list[Instrument]) -> Iterator[Quote]: ...  # tiempo real
```

### 3.3 M3 — Estrategia y Bot

```python
class Strategy(Protocol):                            # bloque del diseñador
    def on_data(self, ctx: StrategyContext) -> list[Order]: ...
    @property
    def params_schema(self) -> ParamSchema: ...

@dataclass(frozen=True)
class BotVersion:
    bot_id: BotId
    version: int
    strategy_id: str
    params: Mapping[str, Any]                         # congelado al publicar (§5.8.1)
    universe: list[Instrument]
    risk_profile_id: str

class BotRegistry(Protocol):
    def publish(self, draft: BotDraft) -> BotVersion: ...   # bifurca nueva versión
    def get(self, bot_id: BotId, version: int | None = None) -> BotVersion: ...
```

### 3.4 M5 — Execution venue y modelos de ejecución enchufables

```python
class ExecutionVenue(Protocol):                      # SandboxLedger | BrokerAdapter
    def submit(self, order: Order, account: AccountRef) -> Fill | OrderAck: ...
    def positions(self, account: AccountRef) -> list[Position]: ...
    def cash(self, account: AccountRef) -> Decimal: ...

class FillPriceModel(Protocol):
    def price(self, order: Order, mkt: MarketSnapshot) -> Decimal: ...   # por defecto: cruzar spread

class SlippageModel(Protocol):
    def adjust(self, price: Decimal, order: Order, mkt: MarketSnapshot) -> Decimal: ...  # por defecto: bps fijos

class CommissionModel(Protocol):
    def fee(self, order: Order, fill_price: Decimal) -> Decimal: ...     # acciones + opciones por contrato

class OptionsPricingModel(Protocol):
    def fill_price(self, ins: Instrument, mkt: MarketSnapshot) -> Decimal: ...
    def mark(self, ins: Instrument, mkt: MarketSnapshot) -> Decimal: ... # MTM entre ejecuciones

# SandboxLedger compone los cuatro modelos de arriba + un EventLedger (M10)
```

### 3.5 M6 — Riesgo

```python
class RiskModel(Protocol):                           # consciente de la clase de activo
    def check(self, order: Order, portfolio: Portfolio) -> RiskDecision: ...

class PositionSizer(Protocol):
    def size(self, signal: Signal, portfolio: Portfolio) -> Decimal: ...

class GuardrailPolicy(Protocol):
    def enforce(self, account: AccountRef) -> GuardrailState: ...        # kill-switch, pérdida diaria
```

### 3.6 M9 — Señales

```python
@dataclass(frozen=True)
class Signal:
    bot_version: BotVersion
    instrument: Instrument
    action: Literal["BUY","SELL","CLOSE"]
    rationale: Rationale            # tesis, señales disparadas, métricas de riesgo, sizing, invalidación
    created_at: datetime

class SignalEngine(Protocol):
    def run(self, bot: BotVersion, ctx: RunContext) -> list[Signal]: ...

class SignalStream(Protocol):
    def publish(self, signal: Signal) -> None: ...
    def subscribe(self, subscription: SubscriptionRef) -> Iterator[Signal]: ...
```

### 3.7 M10 — Ledger resistente a manipulaciones y rendimiento

```python
class EventLedger(Protocol):                         # solo-anexar + encadenado por hash (§5.8.1)
    def append(self, event: LedgerEvent) -> LedgerEntry:   # devuelve entrada con prev_hash + hash
    def verify(self, scope: LedgerScope) -> VerificationResult: ...     # detecta manipulación
    def replay(self, scope: LedgerScope) -> Iterator[LedgerEvent]: ...

class PerformanceCalculator(Protocol):
    def metrics(self, scope: LedgerScope) -> PerformanceRecord: ...     # Sharpe, maxDD, neto, operaciones...
```

### 3.8 M4 — Ciclo de vida y calificación

```python
class BotState(str, Enum):
    DRAFT="draft"; EVALUATION="evaluation"; LISTED="listed"
    SUSPENDED="suspended"; DELISTED="delisted"; LIQUIDATION="liquidation"; RETIRED="retired"

class QualificationCriterion(Protocol):              # componible, enchufable
    def evaluate(self, perf: PerformanceRecord) -> CriterionResult: ...

class QualificationPolicy(Protocol):                 # conjunto de criterios nombrado + versionado
    name: str; version: int
    def assess(self, perf: PerformanceRecord) -> PolicyResult: ...      # aprobado/rechazado + razones

class BotLifecycle(Protocol):
    def transition(self, bot_id: BotId, to: BotState, reason: str) -> None: ...
```

### 3.9 M1 — Identidad y Acceso

```python
class IdentityProvider(Protocol):                    # envoltorio OAuth/OIDC de Authlib
    def begin_login(self, provider: str) -> RedirectUrl: ...
    def complete_login(self, provider: str, cb: CallbackParams) -> Identity: ...

class RoleService(Protocol):
    def roles_of(self, user_id: UserId) -> set[Role]: ...               # acumulativo
    def require(self, user_id: UserId, permission: Permission) -> None:  # lanza si se deniega

class Role(str, Enum):
    USER="user"; DESIGNER="designer"; ADMIN="admin"; ROOT_ADMIN="root_admin"
```

### 3.10 M11 — Suscripciones y Facturación

```python
class BillingProvider(Protocol):                     # adaptador de Stripe Connect
    def charge_subscription(self, sub: Subscription) -> Charge: ...
    def split_and_payout(self, charge: Charge, designer: DesignerRef, commission_pct: Decimal) -> Payout: ...
    def handle_webhook(self, event: WebhookEvent) -> None: ...           # dunning, cancelaciones

class SubscriptionService(Protocol):
    def subscribe(self, user: UserId, bot: BotId) -> Subscription:       # auto-aprovisiona sandbox (M5)
    def cancel(self, sub_id: SubscriptionId) -> None: ...                # corre hasta fin de período
    def on_lapse(self, sub_id: SubscriptionId) -> None: ...              # reglas de respetar-hasta-fin-de-ciclo
```

### 3.11 M13 — Agente / Copiloto

```python
class AgentTool(Protocol):                           # envuelve una capacidad de dominio para el LLM
    name: str; schema: JsonSchema
    def invoke(self, args: dict, principal: Principal) -> ToolResult: ...

class AgentOrchestrator(Protocol):
    def chat(self, principal: Principal, message: str, tools: list[AgentTool]) -> Iterator[Token]: ...
```

> El poder del agente está acotado por las **herramientas** que se le dan y el **RBAC** del que llama — solo puede hacer aquello para lo que el principal está autorizado. Nunca escribe en el ledger ni mueve dinero directamente; invoca los caminos de lectura de M9/M10/M6 y propone acciones.

---

## 4. Flujos clave entre módulos

**Suscribir → simulación en vivo en sandbox:**
`MarketplaceService.subscribe` → `SubscriptionService.subscribe` (M11) → aprovisiona un `SandboxLedger` (M5) para (usuario, bot) → `SignalEngine` (M9) corre la `BotVersion` → las señales pasan por `RiskModel` (M6) → `SandboxLedger` auto-ejecuta vía los cuatro modelos de ejecución → cada evento aterriza en `EventLedger` (M10) → transmitido a la UI por WebSocket (M16) + anotaciones en el gráfico.

**Calificación de bot:**
`SignalEngine` corre en `EVALUATION` → ejecuciones registradas en `EventLedger` (M10) → `PerformanceCalculator` → `QualificationPolicy.assess` (M4) → al aprobar, `BotLifecycle.transition(LISTED)`.

**Pago al diseñador:**
`BillingProvider.charge_subscription` (M11) → si es bot de diseñador, `split_and_payout` con el `commission_pct` del admin desde `ConfigStore` (M14) → auditoría (X).

---

## 5. Límites de módulos y reglas

- **El Fundamento no sabe nada hacia arriba.** `Instrument`, `EventLedger`, `TenantContext`, `AuditLog` no dependen de módulos de negocio.
- **El Dominio de Trading es libre de HTTP y libre de LLM.** Puede correr sin cabeza (backtests, sandbox) sin web ni agente presentes.
- **Un único dueño de escritura por agregado.** Solo M10 anexa al ledger; solo M5 muta posiciones del sandbox; solo M11 toca el estado de facturación.
- **El multi-inquilino se aplica en la capa del repositorio**, no por funcionalidad — cada consulta se acota por `TenantContext`.
- **Los cuatro modelos de ejecución + criterios de calificación son enchufables** (Protocol + registro), seleccionados vía `ConfigStore` (M14).
- **El agente actúa solo a través de `AgentTool`s** controlados por `RoleService` — sin puerta trasera privilegiada.

---

## 6. Orden de construcción sugerido (mapea al MVP §12)

1. **Fundamento** (X): `Instrument`, persistencia/UoW, `TenantContext`, `AuditLog`, `Clock`.
2. **M1 IAM**: login OAuth (Google) + JWT/sesión + RBAC + root admin.
3. **M2 Datos de Mercado**: `MarketDataProvider` de ThinkorSwim/Schwab + `InstrumentCatalog`.
4. **M10 Ledger** + **M5 Sandbox** (con los cuatro modelos de ejecución) — el núcleo de confianza/ejecución.
5. **M3 Bot/Estrategia** + **M6 Riesgo** + **M9 Señales** — hacer que un bot produzca ejecuciones en un sandbox.
6. **M4 Ciclo de vida y Calificación** + **M10 PerformanceCalculator**.
7. **M12 Mercado** + **M11 Suscripciones** (Stripe en modo de prueba) → suscribir auto-aprovisiona un sandbox.
8. **M16 API/WS** + **gráfico en tiempo real** (Lightweight Charts) — la visualización principal de v0.1.
9. **M13 Agente/Copiloto** (explicaciones, narrativas) + **M15 Notificaciones**.
10. Consola **M14 Admin/Config**.
11. **M8 Backtesting** (framework OSS) — puede ir detrás del sandbox, ya que el sandbox es el producto visible.

---

## 7. Espejo de módulos del frontend (breve)

`/packages/core` (TS compartido) refleja el contrato de la API: `auth`, `marketplace`, `subscriptions`, `signals` (WS), `sandbox`, `billing`, `admin`, además de los tipos generados por OpenAPI. `/packages/web` compone estos en áreas funcionales: Mercado, Detalle del Bot, Estudio del Diseñador, Panel del Suscriptor (+ gráfico en vivo), Copiloto, Consola de Admin. Sin lógica de dominio — solo presentación (§9).
