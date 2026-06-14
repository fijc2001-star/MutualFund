# MutualFund — Mercado de Bots de Trading Agéntico

> 🌐 Traducción al español de [`REQUIREMENTS.md`](./REQUIREMENTS.md). En caso de discrepancia, **la versión en inglés es la fuente de verdad**.

> **Resumen en una línea:** Un mercado SaaS donde los miembros diseñan bots de trading y venden sus **flujos de señales** a una comunidad. Los usuarios se suscriben a bots gratuitos o de pago; los diseñadores monetizan sus estrategias; la plataforma se queda con una comisión configurable. *Proceso* de nivel institucional — gestión de riesgo, síntesis de investigación, razonamiento en lenguaje claro — al alcance de las masas.
>
> Los usuarios conservan sus **propias cuentas de corretaje (brokerage)**. La plataforma nunca custodia fondos. Los bots emiten señales; los usuarios actúan sobre ellas (con aprobación) en sus propias cuentas. Copiloto, no piloto automático.

---

## 1. Modelo de Plataforma y Roles (el corazón del producto)

Es un **mercado de dos lados**: los **diseñadores** de bots en el lado de la oferta, los **suscriptores** de señales en el lado de la demanda, con la **plataforma** intermediando y cobrando una comisión.

### 1.1 Roles

| Rol | Capacidades | Cómo se crean |
|-----|-------------|---------------|
| **Usuario (User)** | Explorar el mercado de bots. Suscribirse a flujos de señales de bots **gratuitos** sin costo, o suscribirse a un bot **de pago de un diseñador** por una tarifa recurrente. Conectar su propio bróker; actuar sobre las señales (aprobar para ejecutar). Gestionar suscripciones y facturación. | Rol por defecto al registrarse. |
| **Diseñador (Designer)** | Todo lo que puede hacer un Usuario **más**: diseñar, hacer backtesting, publicar y versionar bots; fijar precios de suscripción; ver ganancias y analíticas de suscriptores; recibir pagos (menos la comisión de la plataforma). | Un Usuario **asciende pagando una prima** (la "prima de diseñador"). |
| **Administrador (Admin)** | Acceso total a la plataforma: gestionar usuarios/roles, moderar bots, fijar configuración global (% de comisión, prima de diseñador, límites), ver todas las analíticas, suspender bots/cuentas, gestionar disputas/reembolsos. | Otorgado por un Admin existente / root admin. |
| **Administrador Raíz (Root Admin)** | Un único super-admin **configurable** con autoridad máxima (puede crear/revocar Admins, cambiar cualquier ajuste global, kill-switch de emergencia). Inicializado desde configuración al desplegar. | Definido vía configuración de la plataforma (env/secret), no por la UI. |

> Los roles son **acumulativos**: Diseñador ⊃ capacidades de Usuario; Admin ⊃ todo. Un usuario puede tener el rol más alto para el que califique.

### 1.2 Bots y Flujos de Señales

- Un **Bot** es una estrategia publicada y versionada que emite un **flujo de señales** (señales de trading clasificadas y explicadas — entradas, salidas, guía de dimensionamiento).
- Una **Suscripción** vincula a un Usuario con el flujo de un Bot. Las suscripciones son **gratuitas** o **de pago** (tarifa recurrente dentro de los límites configurados por la plataforma).
- **Al suscribirse, el sistema aprovisiona automáticamente un sandbox por suscripción** (ver §1.5): un libro mayor (ledger) de paper-trading aislado que reproduce automáticamente las operaciones del bot para que el suscriptor vea una simulación en vivo adaptada a su propia fecha de inicio de suscripción.
- Los usuarios también reciben señales + justificación en la app y por notificación. **La ejecución en vivo en un bróker/exchange real es una etapa posterior** (§1.5).

### 1.2.1 Ciclo de Vida del Bot

`Draft` (Borrador) → `Evaluation` (Evaluación) → `Listed` (Listado) → (`Suspended` / `Delisted`) → `Liquidation` (Liquidación) → `Retired` (Retirado)

- **Draft:** el diseñador construye, configura y hace backtesting; no visible para otros.
- **Evaluation (período de prueba):** el bot corre en vivo en el sandbox y es **monitoreado durante un período configurable por el admin**; debe superar **umbrales de rendimiento configurables por el admin** (p. ej., antigüedad mínima del historial, piso de retorno ajustado por riesgo, techo de drawdown máximo). Aún no suscribible por otros.
- **Listed:** superó la evaluación — aparece en el mercado y es suscribible. El rendimiento sigue registrándose.
- **Suspended / Delisted:** cae por debajo de los umbrales, viola políticas, o la prima del diseñador caduca → **eliminado de las *nuevas* suscripciones**. **Los suscriptores existentes se respetan hasta el final de su ciclo de facturación actual (sin reembolsos, sin corte anticipado)**, tras lo cual la suscripción no se renueva. El bot entra en **Liquidation**.
- **Liquidation (cierre ordenado):** sin nuevas suscripciones; los sandboxes de suscriptores existentes corren solo hasta el final del ciclo de facturación de cada uno. Cuando termina el ciclo de un suscriptor, **el sandbox de ese suscriptor deja de existir** — las posiciones simuladas abiertas se liquidan/cierran y el sandbox (ledger + posiciones) se desmantela (sujeto a la retención del registro de auditoría, §5.11).
- **Retired:** una vez que terminó el último ciclo de suscriptor y todos los sandboxes fueron desmantelados, el bot queda totalmente retirado.

### 1.3 Monetización (todas las tarifas configurables por el Admin)

La plataforma genera ingresos de **dos fuentes**: (1) la prima de **acceso de diseñador**, y (2) las **suscripciones a bots**.

| Palanca | Descripción | ¿Configurable? |
|---------|-------------|----------------|
| **Prima de diseñador** | Tarifa **recurrente** que paga un Usuario para mantener el rol de Diseñador. | ✅ global |
| **Tarifa de suscripción al bot** | Tarifa recurrente, por usuario y por bot. Fijada por el creador del bot dentro del mín/máx definido por el Admin. | ✅ por bot (acotada) |
| **Reparto de ingresos en suscripciones** | **Bot creado por Admin/plataforma → la plataforma se queda el 100%.** **Bot creado por un diseñador → la plataforma retiene un % configurable (variable de admin); el diseñador recibe el resto.** | ✅ % global para bots de diseñador |
| **Bots gratuitos** | Flujos sin costo (bots iniciales provistos por la plataforma y/o niveles gratuitos de diseñadores) para impulsar la adopción. | n/a |
| **Nivel de plataforma (freemium)** | Una suscripción a nivel de plataforma **independiente de las tarifas de bots**, que monetiza *capacidades*. Nivel **Free** (bots gratuitos, sandboxes limitados, posiblemente señales con retraso) vs. nivel **Pro** de pago (señales en tiempo real, más suscripciones simultáneas, copiloto completo, analíticas avanzadas). Compensa el costo de LLM/cómputo y monetiza a quienes navegan pero no compran bots de pago. | ✅ definiciones de nivel configurables por admin |

> **Nota:** El paquete de acceso total (modelo "Netflix") y la facturación por uso medido se posponen (complejidad de reparto de pagos / medición); revisar más adelante. El nivel freemium está **diseñado de antemano pero probablemente llega en la v1.x**, después de que se lance el mercado central.

- **Pagos y desembolsos** fluyen a través de un procesador apto para marketplaces (**Stripe Connect** recomendado): la plataforma cobra a los suscriptores; para bots de diseñador retiene la comisión configurada y paga al diseñador; para bots de plataforma/admin retiene la suscripción completa.

**Ciclo de vida de la suscripción (aplica a la prima de diseñador Y a las suscripciones a bots):**
- **Interrupción involuntaria (falla el pago / rechazo de tarjeta):** tras los reintentos de cobro (dunning), el acceso **caduca** — la caducidad de la prima de diseñador suspende la publicación/ganancias; la caducidad de la suscripción a un bot detiene el flujo de señales.
- **Cancelación voluntaria:** el acceso **se mantiene hasta el final del período pagado actual** y luego no se renueva.
- **Caducidad de la prima del diseñador / retiro de un bot → los suscriptores existentes de sus bots** se **respetan hasta el final del ciclo de facturación actual de cada suscriptor (sin reembolsos)**; solo se bloquean las *nuevas* suscripciones.

### 1.4 Confianza y descubrimiento (esenciales del mercado)

- **Rendimiento verificado:** cada bot muestra un historial transparente y resistente a manipulaciones — rendimiento de backtest *y* de señales en vivo/forward, claramente etiquetado. Sin selección sesgada (cherry-picking).
- **Descubrimiento en el mercado:** explorar/buscar/clasificar bots por tipo de estrategia, clase de activo, perfil de riesgo, rendimiento en vivo, número de suscriptores, calificación.
- **Moderación:** los Admins revisan/suspenden bots; los diseñadores no pueden editar el historial retroactivamente.

### 1.5 Etapas de Ejecución (sandbox ahora, en vivo después)

La plataforma se construye en torno a una abstracción **`ExecutionVenue`** para que las mismas señales del bot puedan dirigirse a un libro mayor simulado hoy y a un mercado real después — sin reescrituras.

**Etapa 1 — Sandbox por suscripción (v1):**
- En cada suscripción, se aprovisiona automáticamente un **sandbox aislado** para el par (usuario, bot) con su **propio ledger**.
- Las operaciones del bot **se ejecutan automáticamente** en ese sandbox; el suscriptor observa una simulación en vivo sembrada desde el inicio de su suscripción.
- **Cada usuario tiene su propia cola de operaciones, ledger de posiciones e historial** por suscripción — completamente aislado de otros usuarios y de la propia ejecución del diseñador.
- Esto también funciona como el sustrato de confianza/verificación: el historial listado de un bot es su rendimiento en el sandbox.
- **Desmantelamiento:** el sandbox de un suscriptor vive durante toda la suscripción. Cuando la suscripción termina — incluso cuando un bot está en **Liquidation** (§1.2.1) y caduca el ciclo de facturación del suscriptor — las posiciones abiertas del sandbox se liquidan y el sandbox (ledger + posiciones) **deja de existir**, conservándose solo lo necesario para el registro de auditoría.

**Etapa 2 — Ejecución en vivo en exchange/bróker (después):**
- El sistema está **diseñado para integrarse con exchanges/brókers reales** y conectar un bot a un mercado en vivo.
- Implementado como implementaciones adicionales de `ExecutionVenue` / `BrokerAdapter`; las capas de mercado, sandbox, roles y facturación quedan intactas.
- La ejecución en vivo reintroduce la **aprobación humana explícita (human-in-the-loop)** y las barreras de riesgo estrictas antes de colocar cualquier orden real (condicionado a la aprobación legal, §11).

---

## 2. Decisiones de Producto (fijadas)

| Decisión | Elección | Justificación |
|----------|----------|---------------|
| **Modelo de negocio** | **SaaS de mercado de bots (Opción B)** | Mercado de dos lados; los usuarios operan sus propias cuentas; la plataforma nunca custodia fondos. |
| **Roles** | **Usuario / Diseñador / Admin (+ Root Admin configurable)** | El rol de Diseñador está condicionado a una prima; el Admin tiene todos los privilegios. |
| **Ingresos** | (1) **Prima de diseñador recurrente** + (2) **suscripciones a bots** — la plataforma se queda el **100%** de los bots de admin/plataforma y un **% configurable** de los bots de diseñador | Ajustable por el admin. |
| **Clases de activo (v1)** | **Acciones (equities) + opciones de EE. UU.** | Mejores datos, mayor soporte de APIs de brókers. |
| **Clases de activo (objetivo de diseño)** | **Núcleo agnóstico a la clase de activo** | Agregar futuros, cripto, forex sin reescrituras. |
| **Usuario objetivo** | **Traders activos** (suscriptores) + **creadores de estrategias** (diseñadores) | De dos lados. |
| **Autonomía (v1)** | **Auto-simulado en un sandbox por usuario** | Al suscribirse, cada usuario obtiene un sandbox + ledger de paper-trading aislado que **ejecuta automáticamente** las operaciones del bot para simulación. **La ejecución en vivo en exchange es una etapa diseñada para después.** |
| **Calificación de bots** | **Período de evaluación + umbrales** | Un bot nuevo debe ser monitoreado durante un **período configurable por el admin** y superar **umbrales de rendimiento** antes de que otros usuarios puedan suscribirse. |

---

## 3. Lo que Vendemos (y lo que NO prometemos)

- **Vendemos:** un mercado de *proceso y acceso* de nivel institucional — controles de riesgo disciplinados, construcción de portafolio, síntesis de investigación, historiales transparentes y razonamiento en lenguaje claro, a una fracción del costo institucional.
- **NO prometemos:** retornos específicos ni "ganarle al mercado". Ni la plataforma ni los diseñadores pueden garantizar rendimiento. El valor defendible es **mejor proceso, transparencia y acceso** — no alfa garantizado.

---

## 4. Principio Arquitectónico Central

> **El LLM razona y comunica. El código determinista decide los números.**

El agente es la capa de **interfaz + orquestación + razonamiento**. Todas las decisiones cuantitativas (dimensionamiento de riesgo, optimización, backtests, griegas de opciones, P&L, atribución de rendimiento) corren en **motores deterministas y testeables** que el agente *invoca como herramientas*. Mantiene los cálculos auditables, repetibles y seguros.

> **Todo corre en el backend de Python.** Los clientes web/móvil son capas de presentación delgadas — ninguna lógica de trading, estrategia, riesgo, bróker, facturación o roles corre en el frontend.

```
        ┌───────────────────────────────────────────────────────┐
        │  Usuario (suscriptor)  Diseñador (creador)   Admin      │
        └───────┬───────────────────┬──────────────────┬─────────┘
                │  suscribir/actuar  │ diseñar/publicar │ configurar/moderar
        ┌───────▼────────────────────▼──────────────────▼─────────┐
        │                 PLATAFORMA (Python / FastAPI)             │
        │  AuthZ y Roles │ Mercado y  │ Suscripciones │ Facturación │
        │  (RBAC)        │ Descubrim. │ y Pagos        │ y Comisión  │
        ├───────────────────────────────────────────────────────────┤
        │           ORQUESTACIÓN DEL AGENTE (LLM, tool-calling)      │
        ├──────┬─────────┬──────────┬──────────┬─────────┬──────────┤
        │Datos │ Motor   │ Optimiz. │ Motor de │Backtest │Ejecución │
        │de    │ Riesgo y│ Portaf.  │ Bot /    │y Seguim.│(adaptad. │
        │Merc. │ Sizing  │          │ Estrateg.│ Rendim. │ de bróker)│
        └───┬──┴────┬────┴────┬─────┴────┬─────┴────┬────┴────┬─────┘
        ┌───▼───────▼─────────▼──────────▼──────────▼─────────▼─────┐
        │   ABSTRACCIÓN DE CLASE DE ACTIVO (interfaz Instrument)    │
        │   Acción | Opción | (Futuro | Cripto | FX ...)            │
        └──────────────────────────────────────────────────────────┘
```

---

## 5. Requisitos Funcionales

### 5.1 Cuentas, Roles y Autorización
- **Autenticación: propia, social primero.** Login OIDC/OAuth vía **Authlib** (Google primero; diseñado para múltiples proveedores — Apple/Microsoft/GitHub). Tras el callback del proveedor, el backend emite su **propio JWT/sesión** y gestiona su vigencia, refresco, revocación y cierre de sesión. Respaldo por email/magic-link solo si se necesitan usuarios sin login social.
- **Vinculación de cuentas:** una misma identidad entre proveedores (emparejada por email verificado) se mapea a una sola cuenta, según una política de vinculación definida.
- **No implementar el protocolo OAuth a mano** — usar Authlib (state/PKCE/intercambio de tokens).
- El registro asigna por defecto **Usuario**. Ascenso a **Diseñador** mediante prima de pago; **Admin** otorgado por Admin/root admin.
- **Control de acceso basado en roles (RBAC)** gestionado y aplicado **en el servidor** en cada solicitud; privilegios acumulativos. (Autenticación = quién eres vía OAuth; autorización = qué puedes hacer, siempre en FastAPI.)
- **Root admin** inicializado desde configuración (env/secret), no editable por la UI normal.

### 5.2 Integración con Brókers
- Conectar el bróker propio del usuario vía API (**v1: Alpaca**; interfaz `BrokerAdapter` para IBKR, Tradier, etc.).
- Leer posiciones/saldos/poder de compra/órdenes; colocar/modificar/cancelar **solo tras aprobación explícita del usuario** (v1).
- **El paper-trading es de primera clase** y es el valor por defecto en el onboarding.

### 5.3 Mercado y Descubrimiento
- Explorar/buscar/filtrar/clasificar bots por clase de activo, tipo de estrategia, riesgo, **rendimiento en vivo**, suscriptores, calificación.
- Página de detalle del bot: descripción, resumen de estrategia, **backtest verificado + historial en vivo**, tarifa, perfil del diseñador.
- Suscribirse / cancelar; gestionar suscripciones activas.

### 5.4 Diseño de Bots (rol Diseñador)
- Crear, configurar, hacer **backtest**, publicar y **versionar** bots.
- Definir qué bloques de construcción `Strategy` usa el bot, parámetros, universo de activos, perfil de riesgo.
- Fijar el precio de suscripción (dentro de los límites del Admin); nivel gratuito opcional.
- Panel de ganancias: suscriptores, ingresos, pagos, comisión descontada.
- El historial de un bot publicado es **inmutable** (sin edición retroactiva del rendimiento).

### 5.5 Flujos de Señales, Simulación en Sandbox y Copiloto
- Los bots suscritos entregan **señales clasificadas y explicadas**: tesis, señales disparadas, métricas de riesgo, lógica de dimensionamiento, condiciones de invalidación.
- **Sandbox por suscripción:** al suscribirse, se aprovisiona automáticamente un ledger de paper-trading aislado para el par (usuario, bot) que **ejecuta automáticamente** las operaciones del bot. Cada usuario tiene su propia **cola de operaciones, posiciones, ledger e historial**, aislados por suscripción.
- Paneles del suscriptor: P&L simulado en vivo, posiciones abiertas, historial de operaciones, y rendimiento vs. el historial principal del bot.
- **Gráfico de señales/posiciones en tiempo real (foco del MVP):** las señales generadas por el bot y los cambios de posición del sandbox se renderizan como **anotaciones en vivo sobre una vista de TradingView Lightweight Charts** — acción del precio con marcadores de compra/venta (▲/▼), líneas de precio de entrada/salida y estado actual de la posición — actualizadas en tiempo real vía WebSocket. (Este es el objetivo inicial de visualización: *ver las señales del bot y los cambios de posición desarrollarse en el gráfico en vivo.*)
- Copiloto conversacional: "explica esta señal", "¿cuál es mi riesgo hoy?", narrativa del portafolio ("qué se movió y por qué").
- Notificaciones de nuevas señales/ejecuciones.

#### 5.5.1 Modelo de Ejecución del Sandbox (enchufable)

El realismo del sandbox se rige por **cuatro modelos independientes y enchufables** detrás de interfaces, de modo que cada dimensión pueda intercambiarse o ampliarse después sin tocar el resto. Cada uno es **configurable por el admin**, y la plataforma incluye **valores por defecto deliberadamente algo conservadores** (prometer de menos en la simulación protege a los usuarios cuando luego operen en vivo).

| Dimensión | Interfaz | Por defecto v1 | Extensiones futuras (enchufables) |
|-----------|----------|----------------|-----------------------------------|
| **Precio de ejecución** | `FillPriceModel` | **Cruzar el spread** (comprar en ask, vender en bid) | último/precio medio, apertura de la siguiente vela, VWAP, etc. |
| **Slippage** | `SlippageModel` | **bps fijos** (configurable) | basado en volumen/volatilidad, modelos de impacto de mercado |
| **Comisiones/tarifas** | `CommissionModel` | **Modelado** — acciones (configurable, puede ser $0) + **tarifas de opciones por contrato** | esquemas escalonados/específicos del bróker |
| **Precio de opciones** | `OptionsPricingModel` | **Cotizaciones históricas reales de opciones** (proveedor de datos, ver §13) | Black-Scholes / precio modelado a partir del subyacente + IV |

- Los cuatro se seleccionan por entorno vía configuración; los modelos y parámetros elegidos se **registran con cada ejecución** en el registro de auditoría para que cualquier historial sea totalmente reproducible.
- Las opciones requieren **valoración a mercado (mark-to-market) entre ejecuciones** (las griegas se mueven continuamente); el `OptionsPricingModel` provee tanto el precio de ejecución como el de MTM.

### 5.6 Motor de Riesgo y Dimensionamiento de Posiciones (determinista)
- Límites por operación y por portafolio: % máximo de posición, concentración por sector, drawdown máximo, nocional/apalancamiento de opciones.
- Dimensionamiento consciente de la volatilidad (volatility targeting / tope de Kelly fraccional).
- Riesgo de opciones: agregación de griegas, riesgo de asignación, exposición al vencimiento.
- **Barreras estrictas** que el agente/bot no puede anular (kill-switch, límite de pérdida diaria). Se aplican a la cuenta propia de cada usuario.

### 5.7 Construcción de Portafolio (determinista)
- Optimizador (media-varianza / paridad de riesgo) con restricciones del motor de riesgo.
- Gancho de conciencia fiscal (selección de lotes, alertas de wash-sale) — diseñar ahora, profundizar después.

### 5.8 Backtesting, Seguimiento de Rendimiento y Calificación de Bots
- Framework de backtest que comparte el **mismo camino de código** que el sandbox/en vivo (sin divergencia). El motor de backtest corre **en el `core` de Python** para que los historiales sean deterministas, reproducibles y se alimenten al ledger resistente a manipulaciones (§5.8.1).
  - **Acelerador del MVP:** en lugar de construir un backtester desde cero, adoptar un **framework de Python de código abierto y gratuito** (p. ej., **backtesting.py** por rapidez de entrega, o VectorBT/Backtrader según crezcan las necesidades), envuelto en `core`. Evolucionar hacia un motor propio con el tiempo sin cambiar la arquitectura.
  - **El backtester de TradingView *no* se usa:** no tiene **API pública** para correr backtests de Pine Script ni extraer resultados programáticamente — no puede alimentar un mercado verificable y multi-inquilino. Los diseñadores pueden prototipar en TradingView manualmente, pero **los historiales de la plataforma provienen solo del motor en `core` + sandbox.**
  - TradingView se aprovecha **solo para graficar** — Lightweight Charts + Widgets embebibles gratuitos (§8).
- **Registro de rendimiento forward/sandbox** por bot — la base de la confianza del mercado; resistente a manipulaciones.
- **Puerta de calificación de bots:** durante la etapa `Evaluation` del ciclo de vida, un bot es monitoreado durante un **período configurable por el admin** y debe superar una **política de calificación** antes de poder ser `Listed` / suscrito por otros usuarios.
- **Política de calificación enchufable:** la puerta es un conjunto componible de reglas **`QualificationCriterion`** detrás de una interfaz — se pueden agregar, quitar o intercambiar criterios sin cambios de código en otras partes. La política está **nombrada y versionada**, de modo que el listón exacto que superó un bot dado siempre quede registrado aunque las reglas evolucionen. Línea base v1 (valores globales por defecto, editables por admin, diseñados para variar luego **por nivel de riesgo**); el bot debe superar **todos**:

  | Criterio | Protege contra | Por defecto v1 |
  |----------|----------------|----------------|
  | Período mínimo de evaluación | Rachas cortas de suerte | **90 días** en vivo en el sandbox |
  | Operaciones cerradas mínimas | Casualidades de muestra pequeña | **≥ 30** |
  | Retorno ajustado por riesgo (Sharpe) | Suerte/apalancamiento disfrazados de habilidad | **≥ 1.0** anualizado |
  | Techo de drawdown máximo | Estrategias propensas a estallar | **≤ 25%** de pico a valle |
  | Piso de rentabilidad | Estrategias con pérdida neta | **Retorno neto positivo** tras tarifas/slippage |
  | Concentración máxima de posición | Una apuesta afortunada cargando el historial | **≤ 30%** del capital del sandbox |

- **Aplicación continua:** los criterios se evalúan incluso después del listado; un bot `Listed` que los incumpla puede marcarse automáticamente para `Suspended`/`Delisted` (§1.2.1).
- Los bots listados se evalúan continuamente; caer por debajo de los umbrales puede disparar `Suspended`/`Delisted` (§1.2.1).

#### 5.8.1 Verificación de Rendimiento Resistente a Manipulaciones

El historial de un bot es la columna vertebral de confianza del mercado y debe ser **demostrablemente inalterado**.

- **Ledger de eventos solo-anexar (append-only):** cada señal, ejecución y conjunto de parámetros es un registro inmutable y solo-anexable — sin UPDATE/DELETE. El rendimiento se **deriva reproduciendo el ledger**, nunca se edita directamente. El ledger es la única fuente de verdad del rendimiento.
- **Encadenamiento por hash (hash-chaining):** cada registro lleva el hash criptográfico del anterior. Alterar cualquier entrada pasada rompe todos los hashes subsecuentes, así que la manipulación — por un diseñador, un interno o un admin — es detectable al instante.
- **Inmutable en prueba/evaluación:** el **ledger de rendimiento registrado durante `Evaluation` (modo de prueba) es inmutable**, así como los **parámetros del bot**. El rendimiento queda ligado al conjunto exacto de parámetros que lo produjo.
- **Versionado inmutable:** cambiar los parámetros de un bot **bifurca una nueva versión del bot** con su propio historial nuevo; el historial y los parámetros de la versión previa quedan congelados. Un diseñador nunca puede "arreglar" una estrategia y conservar el historial viejo.
- **Sin cherry-picking:** el historial público de un bot comienza en `Evaluation`/`Listed` y no puede reiniciarse; los bots abandonados/retirados permanecen en el historial del diseñador (sin el truco de crear-muchos-quedarse-con-el-ganador).
- **Gancho futuro:** raíces Merkle diarias firmadas / notarización externa (p. ej., sellado de tiempo público) para una garantía de "ni siquiera la plataforma puede retrodatar" — diseñado para después.

### 5.9 Facturación, Suscripciones y Pagos
- Pagos del mercado vía **Stripe Connect** (recomendado): cobrar a suscriptores, retener la comisión configurable, pagar a diseñadores.
- Facturación de la prima de diseñador.
- El Admin configura el % de comisión, la prima de diseñador, los límites de tarifas.
- Facturas, reembolsos, gestión de disputas, dunning.

### 5.10 Consola de Administración
- Gestionar usuarios/roles, moderar/suspender bots y cuentas, fijar configuración global, ver analíticas de toda la plataforma, gestionar disputas/reembolsos, kill-switch de emergencia.

### 5.11 Ejecución y Auditoría
- **Abstracción `ExecutionVenue`:** Etapa 1 = **ledger de sandbox** (auto-ejecutado, simulado); Etapa 2 = **bróker/exchange en vivo** (`BrokerAdapter`, con aprobación) — mismo camino de señales, venue intercambiable.
- Manejo inteligente de órdenes detrás de `BrokerAdapter` para la etapa en vivo.
- **Registro de auditoría completo:** cada señal, ejecución simulada/real, aprobación, suscripción y pago se registra con instantánea de justificación/estado.

---

## 6. La Abstracción de Clase de Activo (apuesta clave de extensibilidad)

Modelo común **`Instrument`** + un conjunto pequeño de interfaces para que agregar una clase de activo sea aditivo:

- `Instrument` — símbolo, clase de activo, especificaciones del contrato (multiplicador, vencimiento, strike, tick size).
- `MarketDataProvider` — cotizaciones/barras/cadenas por clase de activo. **Primera implementación: API de ThinkorSwim / Schwab** (la API de TD Ameritrade migró a la API de desarrollador de Schwab; la misma integración puede servir luego como `ExecutionVenue` en vivo). Totalmente **intercambiable** — cualquier otro proveedor (Polygon, Databento, etc.) se enchufa detrás de la interfaz.
- `Strategy` — bloques de construcción que los diseñadores componen en bots; consume datos de `Instrument`, emite señales.
- `RiskModel` — riesgo consciente de la clase de activo (el riesgo de una opción ≠ el de una acción).
- `ExecutionVenue` — a dónde van las órdenes: **`SandboxLedger`** (v1, simulado) o un **`BrokerAdapter`** en vivo (después).
- `BrokerAdapter` — colocación de órdenes en vivo específica del venue/bróker/exchange (un tipo de `ExecutionVenue`).

> Agregar **futuros** o **cripto** después = implementar estas interfaces + un execution venue. El mercado, los roles, la facturación, el agente, el sandbox y la UI quedan intactos.

---

## 7. Requisitos No Funcionales

- **Auditabilidad:** cada decisión automatizada y movimiento de dinero se registra con entradas, justificación y resultado.
- **Determinismo donde importa:** los cálculos de riesgo/optimización/backtest/rendimiento son reproducibles y testeados unitariamente; el LLM nunca está en el camino crítico numérico o de dinero.
- **Confianza e integridad:** registros de rendimiento resistentes a manipulaciones; historial de bot publicado inmutable.
- **Valores por defecto seguros primero:** modo paper por defecto, límites conservadores, aprobación explícita, kill-switch global.
- **Aislamiento multi-inquilino:** estricto aislamiento de datos por inquilino/usuario aplicado en el servidor.
- **Latencia:** copiloto interactivo; generación de señales por lotes/casi en tiempo real (no HFT).
- **Linaje de datos:** fuentes citadas para la investigación mostrada.

---

## 8. Stack Tecnológico (fijado)

| Capa | Elección | Notas |
|------|----------|-------|
| **Backend** | **Python + FastAPI** | Única fuente de verdad: auth/RBAC, mercado, facturación, brókers, estrategias, riesgo, orquestación del agente. REST/JSON + WebSocket, OpenAPI. |
| **Frontend (web)** | **SPA React + TypeScript vía Vite** | Cliente puro, separación limpia FE/BE. Sin SSR (detrás del login). |
| **Móvil (después)** | **React Native + Expo** | Comparte lógica con web vía `core`; UI reconstruida. |
| **Gráficos (precio)** | **TradingView Lightweight Charts** + **Widgets de TradingView** gratuitos | Web. Gratis. Los Widgets (gráfico avanzado, mini-gráfico, ticker, screener) son embebibles directos — usados para acelerar el MVP. |
| **Gráficos (analítica)** | Recharts / visx | Rendimiento, asignación, drawdown, griegas. |
| **Tablas** | **TanStack Table** (+ virtualización) | Listas del mercado, posiciones, órdenes. |
| **Estado de servidor / fetching** | **TanStack Query** | Funciona en web + RN. |
| **Estado de cliente** | **Zustand** | Funciona en web + RN. |
| **Kit de UI web** | **shadcn/ui + Tailwind** | Solo web; móvil usa NativeWind. |
| **UI de chat del agente** | **Vercel AI SDK** | Streaming + renderizado de tool-call/aprobación; apunta a FastAPI. |
| **Tiempo real** | **WebSocket** | Señales, cotizaciones, ejecuciones, tokens del agente. |
| **Pagos** | **Stripe Connect** | Cobros del mercado, reparto de comisión, pagos a diseñadores. |
| **Auth / multi-inquilino** | **Auth propia** — login social OIDC/OAuth vía **Authlib** (Google primero, multi-proveedor), **JWT/sesión** emitidos por el backend, **RBAC** en FastAPI | **Multi-inquilino**; aislamiento por solicitud en el servidor. Social-primero elimina el riesgo de contraseñas; **no implementar el protocolo OAuth a mano — usar Authlib**. Respaldo email/magic-link solo si se necesitan usuarios sin login social. |
| **Proveedor de LLM** | **Por definir (TBD)** | Elegido por calidad de uso de herramientas + razonamiento. |

---

## 9. Estructura del Repositorio (monorepo)

Monorepo vía **pnpm + Turborepo**. La división protege el futuro camino móvil: lógica compartida, no UI compartida.

```
/packages
  /core      ← TS puro: clientes de API, tipos, capa WebSocket, lógica de dominio
              (SIN DOM / SIN APIs de navegador — compartido por web Y móvil)
  /web       ← Vite + React + shadcn/ui            (v1)
  /mobile    ← React Native + Expo                 (después; importa /core)
/backend     ← Python + FastAPI (plataforma + núcleo cuant + agente)
```

**Reglas arquitectónicas:**
- Cero lógica financiera/de trading/facturación/roles en cualquier frontend; toda en el backend de Python.
- El frontend es solo un cliente de presentación.
- **Lógica compartida, presentación reconstruida** — el móvil reutiliza `/core`, nunca componentes de UI web.
- **Sin frameworks de UI compartida por ahora** (sin Tamagui/Solito); revisar solo si el móvil se vuelve primario.

---

## 10. Contrato Frontend ⟷ Backend

- **REST/JSON** para solicitud/respuesta (mercado, suscripciones, posiciones, órdenes, configuración, facturación).
- **WebSocket** para streaming: señales en vivo, cotizaciones, ejecuciones, tokens del agente.
- Clientes tipados generados por **OpenAPI**, consumidos por `/packages/core`.
- Las credenciales de bróker, los secretos de pago y la lógica de roles viven **solo** en el backend, nunca se envían a los clientes.

---

## 11. Cumplimiento y Legal (resolver antes de salir en vivo — no antes de construir)

> ⚠️ **Punto abierto — requiere un abogado de valores antes del lanzamiento con dinero real. El modelo de mercado eleva lo que está en juego frente a una herramienta de un solo usuario.**

- **Los diseñadores que venden señales de trading por una tarifa podrían estar actuando como asesores de inversión no registrados** — y la plataforma podría tener responsabilidad por facilitarlo. Esta es la cuestión legal central y debe evaluarse temprano.
- **Sin garantías de rendimiento** por parte de la plataforma o los diseñadores en ningún material de marketing o copia de la UI.
- El mercado requiere: Términos de Servicio para usuarios *y* diseñadores, divulgaciones de riesgo, acuerdos de diseñador, manejo de pagos/impuestos (p. ej., 1099 para diseñadores de EE. UU.), política de reembolsos/disputas.
- **KYC/AML** probablemente requerido para los pagos a diseñadores (Stripe Connect maneja gran parte).
- Cumplimiento de los términos de las APIs de datos/brókers.
- **Construir + hacer paper-trade libremente ahora; condicionar la ejecución con dinero real y las suscripciones de pago a la aprobación legal.**

---

## 11.5 Panorama Competitivo

> Escaneo de mercado a mediados de 2026. El concepto **no** es novedoso — la categoría existe; nuestra ventaja es la ejecución (copiloto de IA + sandbox por suscripción + confianza verificable) y el enfoque en acciones/opciones.

**Competidores directos (lo más cercano a nuestro modelo):**
- **Collective2 — el referente principal.** Los creadores de estrategias cobran **tarifas de suscripción**; los inversores siguen/copian las operaciones en su **propio bróker** (Interactive Brokers, StoneX, IG); soporta **acciones, opciones, forex, futuros**. Casi nuestro modelo. Fortalezas: historial, amplitud de brókers. Debilidades: UX anticuada, sin copiloto de IA, simulación débil. *Estudiar cómo navegan la regulación de asesores de inversión de EE. UU. (§11).*
- **StockHero** — mercado de bots donde los usuarios construyen bots o **alquilan estrategias**, conectándose a brókers principales vía API ("MetaTrader Signals Market + copy trading social").

**Competidores adyacentes / de categoría:**
- **Copy-trading (atado al bróker, no BYO-bróker):** eToro (CopyTrader — pero opera en el bróker propio de eToro), ZuluTrade, NAGA (mayormente forex/CFD).
- **Mercados de bots de cripto (nuestro modelo, otra clase de activo):** Cryptohopper (Strategy Designer + Marketplace + social — arquitectónicamente el más similar), Mizar, Neuraflow, SaintQuant.
- **Plataformas cuant/de estrategias (construye-lo-tuyo):** QuantConnect (orientada a desarrolladores), Composer (sin código, portafolios de acciones de EE. UU.), TradingView (Pine + comunidad, **sin mercado de ejecución**), MetaTrader Signals Market (forex, atado a MT4/MT5).

**Espacio en blanco / nuestra diferenciación:**
1. **Mercado de bots de acciones + opciones con un copiloto de IA moderno** — C2 tiene el modelo sin la IA/UX; las plataformas de cripto tienen la UX sin las clases de activo.
2. **Sandbox por suscripción** — simulación en vivo personalizada antes de arriesgar dinero real; la mayoría del copy-trading lanza a los usuarios directo a operaciones en vivo.
3. **Historiales resistentes a manipulaciones, encadenados por hash** (§5.8.1) — rendimiento verificable en una categoría criticada habitualmente por el cherry-picking.
4. **Trae tu propio bróker** — frente al jardín amurallado de eToro.

> **Lectura de amenaza:** Collective2 demuestra que el modelo es viable y legalmente navegable para acciones/opciones de EE. UU. — así que el riesgo no es "no hay mercado", sino entrar en una categoría establecida. La diferenciación descansa en IA + sandbox + confianza verificada, no en el concepto en sí.

---

## 12. Alcance Sugerido del MVP (v0.1)

1. Auth + **RBAC** con roles Usuario/Diseñador/Admin y un **root admin** inicializado por configuración.
2. Datos de mercado + abstracciones `Instrument` + `MarketDataProvider` + `ExecutionVenue`; **`SandboxLedger`** como el execution venue de v1.
3. **Diseño de bots** (Diseñador): componer estrategias, backtest, publicar, versionar. 1–2 estrategias de acciones + 1 estrategia de ingresos por opciones como bloques de construcción.
4. **Ciclo de vida del bot + puerta de calificación**: Draft → Evaluation (período + umbrales configurables por admin) → Listed.
5. **Mercado**: explorar/suscribirse a bots gratuitos; detalle del bot con historial verificado.
6. **Sandbox por suscripción**: ledger aislado auto-aprovisionado que ejecuta automáticamente el bot; panel del suscriptor (P&L simulado, posiciones, historial).
7. **Flujos de señales + copiloto**: señales explicadas, ejecuciones del sandbox, narrativa diaria.
   - **Visualización principal de v0.1:** señales del bot + cambios de posición mostrados **en vivo sobre una vista de TradingView Lightweight Charts** (marcadores ▲/▼, líneas de entrada/salida, estado de posición) transmitidos vía WebSocket.
8. Motor de riesgo/dimensionamiento determinista con barreras estrictas.
9. **Esqueleto de facturación**: integración de Stripe Connect para suscripciones de pago, comisión configurable, prima de diseñador, pagos. *(Puede correr en modo de prueba para v0.1.)*
10. **Consola de admin**: gestionar roles, moderar bots, fijar comisión/prima/umbrales de calificación, kill-switch.
11. Registro de auditoría completo.

**Fuera del alcance de v0.1:** ejecución en vivo en exchange/bróker, autonomía total, futuros/cripto/FX (solo interfaces), profundidad de optimización fiscal, app móvil, funciones avanzadas de calificación/sociales.

---

## 13. Registro de Decisiones

Todas las decisiones a continuación están **fijadas** y documentadas en las secciones referenciadas — este es un índice rápido, no la fuente de verdad.

| Decisión | Elección | Sección |
|----------|----------|---------|
| Forma del producto | **Mercado de bots** de dos lados (Usuario / Diseñador / Admin + root admin) | §1, §2 |
| Modelo de negocio | **SaaS (Opción B)** — los usuarios operan sus propias cuentas; la plataforma nunca custodia fondos | §2 |
| Ingresos | **Prima de diseñador** recurrente + suscripciones a bots; la plataforma se queda **100% de los bots de admin**, **% configurable** de los bots de diseñador | §1.3 |
| Ciclo de vida de suscripción | Pago fallido → caducidad tras dunning; cancelar → corre hasta fin de período; bot retirado → suscriptores existentes respetados hasta fin de ciclo, sin reembolsos | §1.2.1, §1.3 |
| Ejecución v1 | **Sandbox por suscripción** (ledger simulado auto-ejecutado); bróker/exchange en vivo es una etapa posterior vía `ExecutionVenue` | §1.5, §5.11 |
| Modelo de ejecución del sandbox | Cuatro modelos enchufables (`FillPriceModel`, `SlippageModel`, `CommissionModel`, `OptionsPricingModel`); valores por defecto conservadores y configurables por admin | §5.5.1 |
| Visualización en tiempo real | Señales del bot + cambios de posición en vivo sobre **TradingView Lightweight Charts** vía WebSocket (vista principal de v0.1) | §5.5 |
| Ciclo de vida y calificación de bots | `Draft → Evaluation → Listed → Suspended/Delisted → Liquidation → Retired`; política **`QualificationCriterion`** enchufable y versionada (línea base: ≥90d, ≥30 ops, Sharpe ≥1.0, maxDD ≤25%, neto+, conc ≤30%) | §1.2.1, §5.8 |
| Verificación de rendimiento | Ledger **encadenado por hash** y solo-anexar; resultados y parámetros de modo evaluación inmutables; **versionado inmutable**; sin cherry-picking | §5.8.1 |
| Backtesting | Motor en `core` de Python, acelerado por un **framework OSS** (backtesting.py / VectorBT / Backtrader); backtester de TradingView **no integrable** | §5.8 |
| Nivel de plataforma | **Freemium** Free/Pro (basado en capacidades, configurable por admin); paquete y medición pospuestos | §1.3 |
| Fuente de datos | **API de ThinkorSwim / Schwab** primero detrás de `MarketDataProvider` intercambiable; proveedor de datos de opciones posible después | §6 |
| Auth | **Propia**, login social OIDC/OAuth vía **Authlib** (Google primero); JWT/sesión en backend; **RBAC en FastAPI** | §5.1 |
| Stack tecnológico | Backend **Python/FastAPI** + web **Vite/React/TS** + móvil **Expo** (después); monorepo pnpm/Turborepo | §8, §9 |
| Multi-inquilino | **Multi-inquilino** desde el día uno | §8 |
| Proveedor de LLM | **Por definir (TBD)** | §8 |
| Pagos | **Stripe Connect** (mercado) | §8 |
| Elegibilidad de diseñador | **Abierta a cualquiera que pague la prima recurrente**; la calidad se controla a **nivel de bot** vía la puerta de calificación, no restringiendo personas | §1.2.1 |

### Aún abierto / pospuesto (no bloquea v0.1)
- [ ] **Revisión legal** concreta antes del lanzamiento con dinero real (§11) — la puerta central previa al lanzamiento.
- [ ] **Proveedor de datos históricos de opciones** (Polygon/Databento) si/cuando se necesite backtesting histórico de opciones.
- [ ] Detalles de la política de **vinculación de cuentas** entre proveedores OAuth.
