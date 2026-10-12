# Fase 5a: equipo por puestos. Plan de implementación

> **Para agentes:** SUB-SKILL REQUERIDA: usá superpowers:subagent-driven-development (recomendada) o superpowers:executing-plans para implementar este plan tarea por tarea. Los pasos usan checkboxes (`- [ ]`) para el seguimiento.

**Objetivo:** que el dispatcher trabaje por **puestos** (una cuenta de un motor), asigne cada tarea según su rol, tamaño y tipo, con respaldo, y no frene cuando una cuenta llega a su límite de uso. Además, que registre métricas por puesto para la fase 5b.

**Arquitectura:**
- **Dos módulos puros nuevos:**
  - `limits.py` detecta un límite de uso y calcula hasta cuándo dura;
  - `routing.py` decide el motor preferido, el respaldo y el puesto concreto.
- **`decide.py`** pasa de "una tarea por motor" a "una tarea por puesto", con prioridad de terminar antes de empezar.
- **`outcomes.py` y `runner.py`** reencolan las tareas cortadas por un límite y marcan el puesto como agotado en `state.json`.
- **`metrics.py`** suma el puesto, las imágenes de Gemini y un registro de cortes, más las agregaciones y las reglas de decisión que va a mostrar la 5b.

**Tecnologías:** Python 3.12, httpx, pytest y respx. Los tests se corren con `uv run --with pytest --with respx python -m pytest -q`, desde `dispatcher/`.

**Spec:** `docs/superpowers/specs/2026-10-12-fase-5a-equipo-por-puestos-design.md`

## Restricciones globales

- Las etiquetas nuevas, tal cual: `size:S`, `size:M`, `size:L`, `kind:architecture`, `needs:images` y `engine:gemini`.
- Sin `size:*`, la tarea cuenta como `M`.
- Si el preferido de un dev o docs está agotado, la tarea espera mientras falten **menos de 2 h** para el reinicio; con más, pasa al respaldo.
- El margen después del reinicio es de **5 minutos**. Si el mensaje no trae hora, se usa **1 hora**.
- `LIMIT_TZ` por defecto es `America/Argentina/Buenos_Aires`, y `GEMINI_IMAGE_USD` por defecto es `0.04`.
- **Sin `SLOTS` en el entorno,** los puestos son `claude:claude:senior,codex:codex:senior`. Así hoy no cambia nada en la mini-PC hasta configurarlo.
- **Las reviews nunca las hace el mismo motor que programó** el PR, que es el `engine:*` del PR.
- **Prioridad de arranque:** comentario `@openhands` > conflicto > fix > review > QA > dev y docs. Dentro de cada tipo, gana el número más bajo.
- **Ni un secreto** en el código, los tests ni los commits.
- Todo el texto de usuario (comentarios, logs) en español rioplatense, como el resto del dispatcher.

## Foco de la review

1. **Un límite sin hora reconocible**, o con un formato de hora nuevo: tiene que caer en 1 hora y no tirar una excepción que trabe el ciclo (tarea 2).
2. **`state.json` viejo**, sin `slot` en las tareas activas ni `slot_exhausted_until`: tiene que cargarse sin error (tarea 3).
3. **Un PR con dos labels `engine:*`** (pasó en nikito#22, con `engine:claude` y `engine:codex`): el motor del dev se toma de forma determinista y la review no puede caer en ninguno de los dos (tarea 4).
4. **Un `metrics.csv` existente con el encabezado viejo:** suma las columnas nuevas sin desalinear las filas (tarea 7).
5. **Una tarea cortada por un límite** que vino de un comentario `@openhands` tiene que volver a correr, y la que vino de un conflicto no puede sumar un intento (tarea 6).

---

### Tarea 1: prueba de Gemini CLI como agente ACP en Canvas (operativa, la hace Claude Code)

**Archivos:**
- Modificar: `canvas/Dockerfile`
- Modificar: `docker-compose.yml` (volumen `gemini-home`)
- Modificar: `docs/bitacora.md`

**Interfaces:**
- **Produce:** el valor de `ENGINE_AGENT_SETTINGS["gemini"]` (el `acp_server` o el `acp_command` que acepte Canvas), que usa la tarea 3. Si la prueba falla, produce la decisión de dejar `gemini` fuera de `SLOTS`.

- [ ] **Paso 1: ver qué servidores ACP conoce Canvas**

Run (en la mini-PC):
```bash
cd /opt/ai-dev-team && docker compose exec -T canvas bash -lc 'grep -rhoE "acp_server[^,]{0,80}" /opt/agent-canvas/node_modules/.bin /acp-node 2>/dev/null | sort | uniq -c | head; ls /acp-node/lib/node_modules'
```
Esperado: la lista de servidores ACP instalados (`@agentclientprotocol/codex-acp`, el de Claude) y los nombres de `acp_server` que conoce Canvas. Anotar si figura `gemini` o un nombre parecido.

- [ ] **Paso 2: instalar Gemini CLI con versión fijada en la imagen**

En `canvas/Dockerfile`, después de la línea de `mcp-image-gemini`:
```dockerfile
# Gemini CLI como tercer motor (fase 5a). Versión fijada; su modo ACP se valida en la prueba.
RUN npm install -g @google/gemini-cli@<versión de al menos 2 semanas, de `npm view @google/gemini-cli time`> \
 && gemini --version
```
En `docker-compose.yml`, en el servicio `canvas`, sumar el volumen `gemini-home:/home/openhands/.gemini` (y declararlo en `volumes:`), igual que `codex-home`.

- [ ] **Paso 3: reconstruir Canvas sin tareas activas y hacer el login**

Run:
```bash
sudo python3 -c "import json;print(json.load(open('/var/lib/docker/volumes/ai-dev-team_dispatcher-state/_data/state.json')).get('active',{}))"
docker compose up -d --no-deps --build canvas
docker compose exec canvas gemini   # Eduardo inicia sesión con su cuenta Gemini Pro ("Login with Google")
```
Esperado: `~/.gemini` queda con las credenciales en el volumen. Si el login con la suscripción no funciona dentro del contenedor, usar `GEMINI_API_KEY` y anotarlo.

- [ ] **Paso 4: crear una conversación de prueba con Gemini por la API de Canvas**

Run (desde el contenedor `dispatcher`, probando primero `{"agent_kind":"acp","acp_server":"gemini-cli"}` y, si Canvas lo rechaza, `{"agent_kind":"acp","acp_command":["gemini","--experimental-acp"]}`):
```bash
docker compose exec -T dispatcher python -c "
import os,httpx
c=httpx.Client(base_url=os.environ['CANVAS_URL'],headers={'X-Session-API-Key':os.environ['CANVAS_API_KEY']},timeout=60)
r=c.post('/api/conversations',json={'agent_settings':{'agent_kind':'acp','acp_server':'gemini-cli'},'workspace':{'working_dir':'/projects/nikito/issue-3'},'initial_message':{'role':'user','content':[{'type':'text','text':'Leé AGENTS.md y respondé con el nombre del proyecto y la lista de tus herramientas MCP. No modifiques nada.'}],'run':True}})
print(r.status_code, r.text[:300])"
```
Esperado: `201` con un id. Pasados unos minutos, `GET /api/conversations?ids=<id>` muestra `finished`, y la respuesta final nombra NIKITO y las herramientas `playwright`, `dart` e `image`.

- [ ] **Paso 5: anotar el resultado y commitear**

En `docs/bitacora.md`, una entrada "Fase 5a, prueba de Gemini CLI" con:
- la versión;
- el valor de `agent_settings` que funcionó;
- el tipo de login;
- si ve los MCP.

Si falló, el motivo y la decisión: `gemini` queda fuera de `SLOTS`, y el QA y el respaldo siguen con Claude y Codex.
```bash
git add canvas/Dockerfile docker-compose.yml docs/bitacora.md
git commit -m "feat(canvas): Gemini CLI como tercer motor ACP (prueba de la fase 5a)"
```

---

### Tarea 2: `limits.py`, detección de límites de uso

**Archivos:**
- Crear: `dispatcher/src/dispatcher/limits.py`
- Test: `dispatcher/tests/test_limits.py`

**Interfaces:**
- **Produce:**
  - `detect_limit(text: str, now: float, tz: str) -> float | None`: devuelve la marca de tiempo (epoch, en segundos) **hasta** la que el puesto queda agotado, ya con el margen de 5 minutos, o `None` si el texto no es un límite;
  - `LIMIT_MARGIN_S = 300`;
  - `DEFAULT_LIMIT_S = 3600`.

- [ ] **Paso 1: escribir los tests que fallan**

```python
# dispatcher/tests/test_limits.py
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from dispatcher.limits import DEFAULT_LIMIT_S, LIMIT_MARGIN_S, detect_limit

TZ = "America/Argentina/Buenos_Aires"


def ts(text, tz=TZ):
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(tz)).timestamp()


NOW = ts("2026-10-11 19:30")


def test_codex_time_only_later_today():
    msg = "ACP error: [-32603] Internal error: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at 10:38 PM."
    assert detect_limit(msg, NOW, TZ) == ts("2026-10-11 22:38") + LIMIT_MARGIN_S


def test_codex_time_only_already_passed_means_tomorrow():
    msg = "You've hit your usage limit. ... try again at 6:00 AM."
    assert detect_limit(msg, NOW, TZ) == ts("2026-10-12 06:00") + LIMIT_MARGIN_S


def test_codex_full_date_with_ordinal():
    msg = "You've hit your usage limit. ... or try again at Oct 12th, 2026 12:39 AM."
    assert detect_limit(msg, NOW, TZ) == ts("2026-10-12 00:39") + LIMIT_MARGIN_S


def test_claude_session_limit_in_utc():
    msg = 'ACP error: [-32603] Internal error: You\'ve hit your session limit · resets 10pm (UTC): {"errorKind": "rate_limit"}'
    now = ts("2026-10-11 21:51", "UTC")
    assert detect_limit(msg, now, TZ) == ts("2026-10-11 22:00", "UTC") + LIMIT_MARGIN_S


def test_gemini_resource_exhausted_without_time_uses_default():
    msg = "RESOURCE_EXHAUSTED You exceeded your current quota, please check your plan and billing details."
    assert detect_limit(msg, NOW, TZ) == NOW + DEFAULT_LIMIT_S


def test_limit_with_unparseable_time_uses_default():
    msg = "You've hit your usage limit. Try again at sometime soon."
    assert detect_limit(msg, NOW, TZ) == NOW + DEFAULT_LIMIT_S


@pytest.mark.parametrize("msg", ["", "flutter test falló: 3 tests", "upstream connect error 503", None])
def test_other_errors_are_not_limits(msg):
    assert detect_limit(msg, NOW, TZ) is None
```

- [ ] **Paso 2: correr y verificar que fallan**

Run: `uv run --with pytest --with respx python -m pytest -q tests/test_limits.py`
Esperado: FALLA con `ModuleNotFoundError: No module named 'dispatcher.limits'`.

- [ ] **Paso 3: implementar**

```python
# dispatcher/src/dispatcher/limits.py
"""Detecta límites de uso de las cuentas de los agentes y calcula hasta cuándo duran. Funciones puras."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

LIMIT_MARGIN_S = 300
DEFAULT_LIMIT_S = 3600

_IS_LIMIT = re.compile(
    r"hit your (?:usage|session) limit|rate_limit|RESOURCE_EXHAUSTED|exceeded your current quota",
    re.IGNORECASE,
)
_CODEX_AT = re.compile(r"try again at\s+(?P<when>[^\n]+?)\.?\s*$", re.IGNORECASE | re.MULTILINE)
_CLAUDE_RESETS = re.compile(r"resets\s+(?P<when>\d{1,2}(?::\d{2})?\s*[ap]m)\s*\((?P<tz>[A-Za-z_/]+)\)", re.IGNORECASE)
_ORDINAL = re.compile(r"(\d{1,2})(st|nd|rd|th)\b")


def _parse_clock(text: str) -> tuple[int, int] | None:
    for fmt in ("%I:%M %p", "%I:%M%p", "%I %p", "%I%p"):
        try:
            t = datetime.strptime(text.strip().upper(), fmt)
            return t.hour, t.minute
        except ValueError:
            continue
    return None


def _next_occurrence(hour: int, minute: int, now: float, tz: ZoneInfo) -> float:
    local_now = datetime.fromtimestamp(now, tz)
    candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate.timestamp() <= now:
        candidate += timedelta(days=1)
    return candidate.timestamp()


def _parse_when(when: str, now: float, tz: ZoneInfo) -> float | None:
    clean = _ORDINAL.sub(r"\1", when.strip())
    for fmt in ("%b %d, %Y %I:%M %p", "%B %d, %Y %I:%M %p"):
        try:
            return datetime.strptime(clean, fmt).replace(tzinfo=tz).timestamp()
        except ValueError:
            continue
    clock = _parse_clock(clean)
    if clock is not None:
        return _next_occurrence(*clock, now, tz)
    return None


def detect_limit(text: str | None, now: float, tz: str) -> float | None:
    """Hasta cuándo queda agotado el puesto (con margen), o None si el texto no es un límite de uso."""
    if not text or not _IS_LIMIT.search(text):
        return None
    until: float | None = None
    if m := _CLAUDE_RESETS.search(text):
        until = _parse_when(m.group("when"), now, ZoneInfo("UTC" if m.group("tz").upper() == "UTC" else m.group("tz")))
    elif m := _CODEX_AT.search(text):
        until = _parse_when(m.group("when"), now, ZoneInfo(tz))
    if until is None:
        return now + DEFAULT_LIMIT_S
    return until + LIMIT_MARGIN_S
```

- [ ] **Paso 4: correr y verificar que pasan**

Run: `uv run --with pytest --with respx python -m pytest -q tests/test_limits.py`
Esperado: PASAN los 9.

- [ ] **Paso 5: commit**

```bash
git add dispatcher/src/dispatcher/limits.py dispatcher/tests/test_limits.py
git commit -m "feat(dispatcher): detección de límites de uso y hora de reinicio"
```

---

### Tarea 3: puestos en `models.py`, `config.py` y `state.py`

**Archivos:**
- Modificar: `dispatcher/src/dispatcher/models.py`
- Modificar: `dispatcher/src/dispatcher/config.py`
- Modificar: `dispatcher/src/dispatcher/state.py`
- Test: `dispatcher/tests/test_config.py`, `dispatcher/tests/test_models.py` y `dispatcher/tests/test_state.py`

**Interfaces:**
- **Produce:**
  - `Slot(name: str, engine: str, tier: str)`, en `models.py`;
  - `ActiveTask.slot: str = ""` y `ActiveTask.comment_id: int | None = None`;
  - `StartTask.slot: str = ""`;
  - `engine_from_labels(labels, default: str | None) -> str | None`, que reconoce `engine:gemini`. **Se elimina** `other_engine`;
  - en `Config`:
    - `slots: tuple[Slot, ...]`;
    - `slot_costs: dict[str, float]`;
    - `limit_tz: str`;
    - `gemini_image_usd: float`;
  - `ENGINES = ("claude", "codex", "gemini")` y `ENGINE_AGENT_SETTINGS["gemini"]`;
  - en `State`, `slot_exhausted_until: dict[str, float]`.
- **Se eliminan** de `Config`: `default_dev_engine`, `qa_engine` y `docs_engine`, que reemplaza la tarea 4. Si quedan `DEFAULT_DEV_ENGINE`, `QA_ENGINE` o `DOCS_ENGINE` en el `.env`, se ignoran.

- [ ] **Paso 1: escribir los tests que fallan**

En `dispatcher/tests/test_config.py`:
- reemplazar `assert cfg.default_dev_engine == "codex"` por los asserts de puestos de abajo;
- borrar `("DEFAULT_DEV_ENGINE", "gemini")` del parametrize;
- reemplazar las aserciones de `qa_engine` y `docs_engine` por `cfg.docs_only_repos`;
- sumar:
```python
from dispatcher.models import Slot


def test_default_slots_keep_one_per_current_engine():
    cfg = Config.from_env(BASE)
    assert cfg.slots == (Slot("claude", "claude", "senior"), Slot("codex", "codex", "senior"))
    assert (cfg.limit_tz, cfg.gemini_image_usd, cfg.slot_costs) == ("America/Argentina/Buenos_Aires", 0.04, {})


def test_slots_and_costs_from_env():
    env = {**BASE, "SLOTS": "claude-senior:claude:senior, codex-senior:codex:senior, gemini:gemini:senior",
           "SLOT_COST_CLAUDE_SENIOR": "100", "SLOT_COST_GEMINI": "20", "LIMIT_TZ": "UTC", "GEMINI_IMAGE_USD": "0.039"}
    cfg = Config.from_env(env)
    assert [s.name for s in cfg.slots] == ["claude-senior", "codex-senior", "gemini"]
    assert cfg.slot_costs == {"claude-senior": 100.0, "gemini": 20.0}
    assert (cfg.limit_tz, cfg.gemini_image_usd) == ("UTC", 0.039)


@pytest.mark.parametrize("value", ["solo-nombre", "x:openai:senior", "a:claude:senior,a:codex:senior"])
def test_invalid_slots_are_rejected(value):
    with pytest.raises(ConfigError, match="SLOTS"):
        Config.from_env({**BASE, "SLOTS": value})
```
En `dispatcher/tests/test_models.py`, reemplazar el test de `other_engine` por:
```python
def test_engine_from_labels_knows_gemini_and_has_no_default():
    assert engine_from_labels(frozenset({"engine:gemini"}), None) == "gemini"
    assert engine_from_labels(frozenset(), None) is None
    assert engine_from_labels(frozenset({"engine:codex", "engine:claude"}), None) == "claude"
```
y sacar `other_engine` del import. En `dispatcher/tests/test_state.py`, sumar:
```python
def test_old_state_without_slots_loads(tmp_path):
    p = tmp_path / "state.json"
    p.write_text('{"active": {"qr#1": {"repo": "qr", "number": 1, "kind": "issue", "role": "dev", "engine": "codex", '
                 '"trigger": "label", "conversation_id": "c", "started_at": 1.0, "workspace": "/w"}}}')
    state = StateStore(p).load()
    assert state.active["qr#1"].slot == "" and state.slot_exhausted_until == {}


def test_slot_exhaustion_round_trips(tmp_path):
    store = StateStore(tmp_path / "state.json")
    state = State(slot_exhausted_until={"codex-senior": 123.0})
    store.save(state)
    assert store.load().slot_exhausted_until == {"codex-senior": 123.0}
```
(con `from dispatcher.state import State, StateStore` si no está importado).

- [ ] **Paso 2: correr y verificar que fallan**

Run: `uv run --with pytest --with respx python -m pytest -q tests/test_config.py tests/test_models.py tests/test_state.py`
Esperado: FALLAN por `ImportError: cannot import name 'Slot'` y atributos faltantes.

- [ ] **Paso 3: implementar**

En `models.py`, reemplazar `other_engine` y `engine_from_labels` por:
```python
@dataclass(frozen=True)
class Slot:
    """Un puesto: una cuenta de un motor, con un nivel."""

    name: str
    engine: str
    tier: str


def engine_from_labels(labels: frozenset[str], default: str | None) -> str | None:
    # Orden fijo: si un PR quedó con dos engine:* (pasó en nikito#22), gana siempre el mismo.
    for engine in ("claude", "codex", "gemini"):
        if f"engine:{engine}" in labels:
            return engine
    return default
```
Al final de `ActiveTask` (después de `workspace: str`) sumar `slot: str = ""` y `comment_id: int | None = None`. Al final de `StartTask` sumar `slot: str = ""`.

En `config.py`:
- `ENGINES = ("claude", "codex", "gemini")`;
- en `ENGINE_AGENT_SETTINGS`, `"gemini": {"agent_kind": "acp", "acp_server": "gemini-cli"}`, o el valor que dejó la tarea 1;
- borrar los campos `default_dev_engine`, `qa_engine` y `docs_engine`, y su lectura en `from_env` (con la función `engine_var` y la variable `engine`);
- sumar los campos:
```python
    slots: tuple[Slot, ...] = (Slot("claude", "claude", "senior"), Slot("codex", "codex", "senior"))
    slot_costs: dict[str, float] = field(default_factory=dict)
    limit_tz: str = "America/Argentina/Buenos_Aires"
    gemini_image_usd: float = 0.04
```
(con `from dataclasses import dataclass, field` y `from .models import Slot`). En `from_env`, antes del `return`:
```python
        def parse_slots() -> tuple[Slot, ...]:
            raw = env.get("SLOTS", "").strip()
            if not raw:
                return (Slot("claude", "claude", "senior"), Slot("codex", "codex", "senior"))
            slots: list[Slot] = []
            for part in (p.strip() for p in raw.split(",") if p.strip()):
                bits = part.split(":")
                if len(bits) != 3 or bits[1] not in ENGINES or not bits[0]:
                    raise ConfigError(f"SLOTS: cada puesto es nombre:motor:nivel con motor en {ENGINES}, no {part!r}")
                slots.append(Slot(*bits))
            if len({s.name for s in slots}) != len(slots):
                raise ConfigError("SLOTS tiene nombres de puesto repetidos")
            return tuple(slots)

        slots = parse_slots()
        costs = {}
        for s in slots:
            raw = env.get(f"SLOT_COST_{s.name.upper().replace('-', '_')}", "").strip()
            if raw:
                costs[s.name] = float(raw)
```
Y en el `cls(...)`: `slots=slots, slot_costs=costs, limit_tz=env.get("LIMIT_TZ", "").strip() or "America/Argentina/Buenos_Aires", gemini_image_usd=float(env.get("GEMINI_IMAGE_USD", "").strip() or 0.04),`.

En `state.py`:
- sumar `slot_exhausted_until: dict[str, float] = field(default_factory=dict)` a `State`;
- en `load`, `slot_exhausted_until={k: float(v) for k, v in data.get("slot_exhausted_until", {}).items()}`;
- en `save`, `"slot_exhausted_until": state.slot_exhausted_until`.

`ActiveTask(**v)` ya admite el estado viejo porque `slot` y `comment_id` tienen valor por defecto.

- [ ] **Paso 4: correr los tests de estos módulos**

Run: `uv run --with pytest --with respx python -m pytest -q tests/test_config.py tests/test_models.py tests/test_state.py`
Esperado: PASAN. (`test_decide.py` y otros van a fallar por `other_engine` y `cfg.qa_engine`; los arreglan las tareas 4 y 5, que van seguidas. No commitear con la suite completa rota: el commit va al final de la tarea 5.)

- [ ] **Paso 5: seguir directo con la tarea 4.** El commit es conjunto, al final de la tarea 5.

---

### Tarea 4: `routing.py`, preferencias y elección de puesto

**Archivos:**
- Crear: `dispatcher/src/dispatcher/routing.py`
- Test: `dispatcher/tests/test_routing.py`

**Interfaces:**
- **Consume:** `Slot` y `engine_from_labels` (tarea 3).
- **Produce:**
  - `LABEL_ARCH = "kind:architecture"`, `LABEL_IMAGES = "needs:images"` y `LONG_EXHAUSTION_S = 7200`;
  - `task_size(labels) -> str`, que devuelve `"S"`, `"M"` o `"L"`;
  - `preferences(role: str, labels: frozenset[str], kind: str) -> tuple[tuple[str, ...], bool]`: los motores en orden de preferencia y si la tarea espera al primero. Para los PRs, el `engine:*` del PR es el motor del dev;
  - `choose_slot(prefs, waits, slots, busy: set[str], exhausted: dict[str, float], now: float) -> Slot | None`.

- [ ] **Paso 1: escribir los tests que fallan**

```python
# dispatcher/tests/test_routing.py
import pytest

from dispatcher.models import Slot
from dispatcher.routing import LONG_EXHAUSTION_S, choose_slot, preferences, task_size

SLOTS = (Slot("claude-senior", "claude", "senior"), Slot("codex-senior", "codex", "senior"), Slot("gemini", "gemini", "senior"))
NOW = 1000.0


def L(*labels):
    return frozenset(labels)


def test_size_defaults_to_m():
    assert task_size(L()) == "M" and task_size(L("size:L")) == "L" and task_size(L("size:S")) == "S"


@pytest.mark.parametrize("labels,expected", [
    (L("size:L"), (("claude", "codex"), True)),
    (L("kind:architecture", "size:S"), (("claude", "codex"), True)),
    (L("size:M"), (("codex", "gemini", "claude"), True)),
    (L(), (("codex", "gemini", "claude"), True)),
    (L("needs:images"), (("codex", "gemini"), True)),
    (L("engine:gemini", "size:L"), (("gemini",), True)),
])
def test_dev_preferences(labels, expected):
    assert preferences("dev", labels, "issue") == expected


def test_docs_preferences_do_not_wait():
    assert preferences("docs", L(), "issue") == (("codex", "gemini", "claude"), False)


@pytest.mark.parametrize("labels,expected", [
    (L("engine:codex"), ("claude", "gemini")),
    (L("engine:gemini"), ("claude", "codex")),
    (L("engine:claude"), ("codex", "gemini")),
    (L("engine:claude", "engine:codex"), ("gemini",)),
    (L(), ("claude", "gemini")),
])
def test_review_never_uses_the_dev_engine(labels, expected):
    assert preferences("review", labels, "pr") == (expected, False)


def test_qa_prefers_gemini():
    assert preferences("qa", L("engine:codex"), "pr") == (("gemini", "codex", "claude"), False)


def test_fix_prefers_the_dev_engine():
    assert preferences("fix", L("engine:claude"), "pr") == (("claude", "codex", "gemini"), False)
    assert preferences("fix", L(), "pr") == (("codex", "claude", "gemini"), False)


def test_choose_free_preferred_slot():
    assert choose_slot(("codex", "gemini"), True, SLOTS, set(), {}, NOW).name == "codex-senior"


def test_dev_waits_while_preferred_is_busy():
    assert choose_slot(("codex", "gemini"), True, SLOTS, {"codex-senior"}, {}, NOW) is None


def test_non_waiting_task_uses_fallback_when_busy():
    assert choose_slot(("gemini", "codex"), False, SLOTS, {"gemini"}, {}, NOW).name == "codex-senior"


def test_dev_waits_for_short_exhaustion_but_moves_on_long_one():
    short = {"codex-senior": NOW + LONG_EXHAUSTION_S - 1}
    long = {"codex-senior": NOW + LONG_EXHAUSTION_S + 1}
    assert choose_slot(("codex", "gemini"), True, SLOTS, set(), short, NOW) is None
    assert choose_slot(("codex", "gemini"), True, SLOTS, set(), long, NOW).name == "gemini"


def test_expired_exhaustion_is_ignored():
    assert choose_slot(("codex",), True, SLOTS, set(), {"codex-senior": NOW - 1}, NOW).name == "codex-senior"


def test_forced_engine_never_falls_back():
    assert choose_slot(("gemini",), True, SLOTS, set(), {"gemini": NOW + 99999}, NOW) is None


def test_engines_without_slots_are_skipped():
    two = SLOTS[:2]
    assert choose_slot(("gemini", "codex"), False, two, set(), {}, NOW).name == "codex-senior"
```

- [ ] **Paso 2: correr y verificar que fallan**

Run: `uv run --with pytest --with respx python -m pytest -q tests/test_routing.py`
Esperado: FALLA con `ModuleNotFoundError: No module named 'dispatcher.routing'`.

- [ ] **Paso 3: implementar**

```python
# dispatcher/src/dispatcher/routing.py
"""Qué motor y qué puesto toma cada tarea (spec fase 5a, sección 4). Funciones puras."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .models import Slot, engine_from_labels

LABEL_ARCH = "kind:architecture"
LABEL_IMAGES = "needs:images"
LONG_EXHAUSTION_S = 7200  # un dev deja de esperar a su puesto si falta más que esto para el reinicio
ALL_ENGINES = ("claude", "codex", "gemini")


def task_size(labels: frozenset[str]) -> str:
    for size in ("S", "L"):
        if f"size:{size}" in labels:
            return size
    return "M"


def _dev_engines(labels: frozenset[str]) -> set[str]:
    return {e for e in ALL_ENGINES if f"engine:{e}" in labels}


def preferences(role: str, labels: frozenset[str], kind: str) -> tuple[tuple[str, ...], bool]:
    """Motores en orden de preferencia y si la tarea espera al primero en vez de usar el respaldo."""
    if kind == "issue":
        forced = engine_from_labels(labels, None)
        if forced is not None:
            return (forced,), True
        if role == "docs":
            return ("codex", "gemini", "claude"), False
        if LABEL_ARCH in labels or task_size(labels) == "L":
            return ("claude", "codex"), True
        if LABEL_IMAGES in labels:
            return ("codex", "gemini"), True
        return ("codex", "gemini", "claude"), True
    # PR: los engine:* dicen quién programó.
    dev = engine_from_labels(labels, None)
    if role == "review":
        order = ("codex", "gemini") if dev == "claude" else ("claude", "codex", "gemini")
        excluded = _dev_engines(labels) or {"codex"}
        return tuple(e for e in order if e not in excluded), False
    if role == "qa":
        return ("gemini", "codex", "claude"), False
    base = dev or "codex"
    return (base, *[e for e in ("codex", "claude", "gemini") if e != base]), False


def choose_slot(
    prefs: Iterable[str], waits: bool, slots: Iterable[Slot], busy: set[str],
    exhausted: Mapping[str, float], now: float,
) -> Slot | None:
    slots = list(slots)
    for i, engine in enumerate(prefs):
        own = [s for s in slots if s.engine == engine]
        if not own:
            continue
        available = [s for s in own if exhausted.get(s.name, 0.0) <= now]
        free = [s for s in available if s.name not in busy]
        if free:
            return free[0]
        if i == 0 and waits:
            if available:
                return None  # ocupado: el dev espera a su puesto
            soonest = min(exhausted[s.name] for s in own)
            if soonest - now < LONG_EXHAUSTION_S:
                return None  # agotado por poco: espera el reinicio
    return None
```
Nota: en `test_review_never_uses_the_dev_engine` con `L()` (un PR sin `engine:*`), `excluded = {"codex"}`, porque el motor por defecto del dev era Codex. Eso da `("claude", "gemini")`, que coincide con el test.

- [ ] **Paso 4: correr y verificar que pasan**

Run: `uv run --with pytest --with respx python -m pytest -q tests/test_routing.py`
Esperado: PASAN todos.

- [ ] **Paso 5: seguir con la tarea 5.** El commit es conjunto.

---

### Tarea 5: `decide.py` por puesto y con prioridad

**Archivos:**
- Modificar: `dispatcher/src/dispatcher/decide.py`
- Test: `dispatcher/tests/test_decide.py`

**Interfaces:**
- **Consume:**
  - `preferences` y `choose_slot` (tarea 4);
  - `Config.slots` y `State.slot_exhausted_until` (tarea 3);
  - `StartTask.slot`.
- **Produce:** cada `StartTask` sale con `engine` y `slot` resueltos. Las tareas activas ocupan su `slot`, o su `engine` si son tareas viejas con el `slot` vacío.

- [ ] **Paso 1: escribir y ajustar los tests**

En `dispatcher/tests/test_decide.py`:
- `test_issue_with_agent_dev_starts_dev_task_with_default_engine`: esperar `StartTask(issue(1, "agent:dev"), "dev", "codex", "label", slot="codex")`;
- `test_issue_with_agent_docs_starts_docs_with_docs_engine`: el motor esperado pasa a ser `"codex"`, porque docs prefiere Codex;
- `test_one_task_per_engine`: por la prioridad de terminar antes de empezar, el orden esperado pasa a `[(5, "claude"), (1, "codex")]` (la review va antes que el dev);
- el test que usa `dataclasses.replace(cfg, qa_engine="claude")`: reemplazarlo por uno que use puestos, con `cfg2 = dataclasses.replace(cfg, slots=(Slot("claude","claude","senior"),))`, y esperar el QA en `claude`.

Sumar:
```python
from dispatcher.models import Slot

THREE = (Slot("claude-senior", "claude", "senior"), Slot("codex-senior", "codex", "senior"), Slot("gemini", "gemini", "senior"))


def test_qa_goes_to_gemini_slot(cfg):
    cfg3 = dataclasses.replace(cfg, slots=THREE)
    [start] = starts(decide([pr(5, "agent:qa", "engine:codex")], [], {}, State(), cfg3, NOW))
    assert (start.engine, start.slot) == ("gemini", "gemini")


def test_size_l_goes_to_claude(cfg):
    cfg3 = dataclasses.replace(cfg, slots=THREE)
    [start] = starts(decide([issue(1, "agent:dev", "size:L")], [], {}, State(), cfg3, NOW))
    assert start.slot == "claude-senior"


def test_finish_before_start_priority(cfg):
    cfg1 = dataclasses.replace(cfg, slots=(Slot("codex-senior", "codex", "senior"),))
    items = [issue(1, "agent:dev"), pr(9, "agent:fix", "engine:codex")]
    [start] = starts(decide(items, [], {}, State(), cfg1, NOW))
    assert (start.item.number, start.role) == (9, "fix")


def test_exhausted_slot_is_not_used_and_review_falls_back(cfg):
    cfg3 = dataclasses.replace(cfg, slots=THREE)
    state = State(slot_exhausted_until={"claude-senior": NOW + 600})
    [start] = starts(decide([pr(5, "agent:review", "engine:codex")], [], {}, state, cfg3, NOW))
    assert start.slot == "gemini"


def test_two_slots_of_different_engines_run_in_parallel(cfg):
    cfg3 = dataclasses.replace(cfg, slots=THREE)
    items = [issue(1, "agent:dev"), issue(2, "agent:dev", "size:L"), pr(5, "agent:qa", "engine:codex")]
    result = {s.item.number: s.slot for s in starts(decide(items, [], {}, State(), cfg3, NOW))}
    assert result == {1: "codex-senior", 2: "claude-senior", 5: "gemini"}


def test_active_task_without_slot_occupies_its_engine(cfg):
    state = state_with(active(7, engine="codex"))
    assert starts(decide([issue(1, "agent:dev")], [], {"c1": ConvInfo("c1", "running")}, state, cfg, NOW)) == []
```
(Importar `ConvInfo` desde `dispatcher.models` si hace falta.)

- [ ] **Paso 2: correr y verificar que fallan**

Run: `uv run --with pytest --with respx python -m pytest -q tests/test_decide.py`
Esperado: FALLAN los tests nuevos y los ajustados.

- [ ] **Paso 3: implementar**

En `decide.py`:
- Imports: sacar `other_engine` y sumar `from .routing import choose_slot, preferences`.
- Reemplazar `busy_engines = {t.engine for t in state.active.values()}` por `busy_slots = {t.slot or t.engine for t in state.active.values()}`.
- En el bloque de conflictos, crear la tarea **sin** motor: `StartTask(item, "fix", "", "conflict", CONFLICT_INSTRUCTION)`.
- En `_comment_candidates`, sacar el cálculo de `engine` y crear `StartTask(item, role, "", "comment", comment.body, comment.id)`.
- En `_label_candidates`, crear las tareas con `engine=""`: `StartTask(item, "docs", "", "label")`, `StartTask(item, "dev", "", "label")`, `StartTask(item, "fix", "", "label")`, `StartTask(item, "review", "", "label")` y `StartTask(item, "qa", "", "label")`.
- Ordenar los candidatos por label y reemplazar el bucle final por la asignación:
```python
ROLE_PRIORITY = {"fix": 0, "review": 1, "qa": 2, "dev": 3, "docs": 3}

    label_candidates.sort(key=lambda c: (ROLE_PRIORITY[c.role], c.item.repo, c.item.number))
    candidates = [*_comment_candidates(items, comments, state, cfg), *conflict_candidates, *label_candidates]
    for candidate in candidates:
        key = candidate.item.key
        if key in busy_items or key in started_items:
            continue
        prefs, waits = preferences(candidate.role, candidate.item.labels, candidate.item.kind)
        slot = choose_slot(prefs, waits, cfg.slots, busy_slots, state.slot_exhausted_until, now)
        if slot is None:
            continue
        actions.append(dataclasses.replace(candidate, engine=slot.engine, slot=slot.name))
        busy_slots.add(slot.name)
        started_items.add(key)
    return actions
```
(con `import dataclasses` arriba y `ROLE_PRIORITY` a nivel de módulo).

- [ ] **Paso 4: correr toda la suite**

Run: `uv run --with pytest --with respx python -m pytest -q`
Esperado: PASAN todos. Si falla algún test de `test_runner.py` porque el fake de Canvas recibe `engine`, revisar que `runner._start` siga pasándole `a.engine` (no cambia). Si un test compara `StartTask` completos, sumarle `slot="codex"` o `slot="claude"`.

- [ ] **Paso 5: commit de las tareas 3, 4 y 5**

```bash
git add dispatcher/src/dispatcher/models.py dispatcher/src/dispatcher/config.py dispatcher/src/dispatcher/state.py \
  dispatcher/src/dispatcher/routing.py dispatcher/src/dispatcher/decide.py dispatcher/tests/
git commit -m "feat(dispatcher): puestos, asignación por rol y tamaño, y prioridad de terminar antes de empezar"
```

---

### Tarea 6: corte por límite en `outcomes.py` y `runner.py`

**Archivos:**
- Modificar: `dispatcher/src/dispatcher/outcomes.py`
- Modificar: `dispatcher/src/dispatcher/runner.py`
- Test: `dispatcher/tests/test_outcomes.py` y `dispatcher/tests/test_runner.py`

**Interfaces:**
- **Consume:**
  - `detect_limit` (tarea 2);
  - `ActiveTask.slot` y `comment_id` (tarea 3);
  - `State.slot_exhausted_until`.
- **Produce:**
  - `Outcome.limited_until: float | None = None`;
  - el resultado `"limite"` en las métricas;
  - `runner._start` guarda `slot` y `comment_id` en `ActiveTask`.

- [ ] **Paso 1: escribir los tests que fallan**

En `dispatcher/tests/test_outcomes.py`:
```python
LIMIT_MSG = "ACP error: You've hit your usage limit. ... try again at 10:38 PM."


@pytest.mark.parametrize("role,trigger_label", [("dev", "agent:dev"), ("review", "agent:review"), ("qa", "agent:qa"), ("fix", "agent:fix")])
def test_usage_limit_requeues_without_needs_human(role, trigger_label):
    t = task(role=role, kind="issue" if role == "dev" else "pr")
    out = outcome_for(t, "error", LIMIT_MSG, frozenset(), None, 1, 2, qa_rounds=1, now=1_000.0, tz="UTC")
    assert out.result == "limite" and out.limited_until is not None
    assert AddLabels(3, ("needs:human",)) not in out.ops
    assert RemoveLabel(3, "agent:working") in out.ops and AddLabels(3, (trigger_label,)) in out.ops
    assert (out.review_rounds, out.qa_rounds) == (1, 1)
    [comment] = [op for op in out.ops if isinstance(op, PostComment)]
    assert "sin cupo" in comment.body


def test_comment_or_conflict_task_hit_by_limit_does_not_readd_label():
    out = outcome_for(task(trigger="comment"), "error", LIMIT_MSG, frozenset(), None, 0, 2, now=1_000.0, tz="UTC")
    assert out.result == "limite"
    assert not [op for op in out.ops if isinstance(op, AddLabels)]


def test_other_errors_still_escalate():
    out = outcome_for(task(), "error", "flutter test falló", frozenset(), None, 0, 2, now=1_000.0, tz="UTC")
    assert out.result == "needs_human" and out.limited_until is None
```
En `dispatcher/tests/test_runner.py`, sumar un test que use el patrón de los existentes (el fake de Canvas con una conversación en `error`). Ver `test_timeout_pauses_and_escalates` como molde: crear un issue `agent:dev`, correr un ciclo para que arranque, poner la conversación en `error` con la respuesta final `LIMIT_MSG` en el fake, y correr otro ciclo. Verificar:
```python
    state = store.load()
    assert state.slot_exhausted_until["codex"] > clock.now
    assert "agent:dev" in github.labels(1) and "needs:human" not in github.labels(1)
    assert state.active == {}
```
Y otro test con un comentario `@openhands` cortado por límite: después del segundo ciclo, `comment.id not in state.processed_comments`.

- [ ] **Paso 2: correr y verificar que fallan**

Run: `uv run --with pytest --with respx python -m pytest -q tests/test_outcomes.py tests/test_runner.py`
Esperado: FALLAN porque `outcome_for` no acepta `now` ni `tz`.

- [ ] **Paso 3: implementar**

En `outcomes.py`:
- sumar `limited_until: float | None = None` a `Outcome`;
- importar `from .limits import detect_limit`;
- cambiar la firma a `outcome_for(task, status, final_response, current_labels, pr, rounds, max_rounds, qa_rounds=0, now: float = 0.0, tz: str = "UTC")`;
- justo después de `def escalate(...)`, y **antes** del `if status not in NORMAL_STATUSES:`:
```python
    if status not in NORMAL_STATUSES and (until := detect_limit(final_response, now, tz)) is not None:
        # Límite de uso de la cuenta: no es culpa del trabajo. La tarea vuelve a la fila como estaba.
        ops = [RemoveLabel(n, LABEL_WORKING)]
        if task.trigger == "label":
            ops.append(AddLabels(n, (TRIGGER_LABELS[task.role],)))
        hhmm = time.strftime("%H:%M", time.gmtime(until))
        ops.append(PostComment(
            n,
            f"⏳ `{task.slot or task.engine}` se quedó sin cupo (hasta las {hhmm} UTC). "
            "La tarea vuelve a la fila: la toma otro puesto disponible o este mismo cuando se reinicie.",
        ))
        return Outcome("limite", tuple(ops), rounds, qa_rounds, until)
```
(con `import time`). Nota: la hora del comentario va en UTC. El spec pide "hasta HH:MM; sigue <otro>"; el plan simplifica a un mensaje genérico, y la tarea 9 ajusta esa línea del spec.

En `runner.py`:
- en `_start`, crear el `ActiveTask` con `slot=a.slot, comment_id=a.comment_id`;
- en `_finish`, pasar `now=now, tz=self.cfg.limit_tz` a `outcome_for`;
- después de aplicar las operaciones:
```python
        if outcome.limited_until is not None:
            state.slot_exhausted_until[task.slot or task.engine] = outcome.limited_until
            if task.comment_id is not None:
                state.processed_comments.discard(task.comment_id)  # el @openhands vuelve a correr
            if task.trigger == "conflict":
                state.conflict_attempts[task.key] = max(0, state.conflict_attempts.get(task.key, 1) - 1)
```
Además, limpiar los cortes vencidos al principio de `run_once`, después de cargar el estado:
```python
        state.slot_exhausted_until = {k: v for k, v in state.slot_exhausted_until.items() if v > now}
```

- [ ] **Paso 4: correr toda la suite**

Run: `uv run --with pytest --with respx python -m pytest -q`
Esperado: PASAN todos.

- [ ] **Paso 5: commit**

```bash
git add dispatcher/src/dispatcher/outcomes.py dispatcher/src/dispatcher/runner.py dispatcher/tests/
git commit -m "feat(dispatcher): una tarea cortada por límite de uso vuelve a la fila y el puesto queda agotado"
```

---

### Tarea 7: métricas por puesto, cortes e imágenes de Gemini

**Archivos:**
- Modificar: `dispatcher/src/dispatcher/metrics.py`
- Modificar: `dispatcher/src/dispatcher/canvas.py`
- Modificar: `dispatcher/src/dispatcher/runner.py`
- Test: `dispatcher/tests/test_metrics.py`, `dispatcher/tests/test_canvas.py` y `dispatcher/tests/fakes.py`

**Interfaces:**
- **Consume:** `ActiveTask.slot` y `Outcome.limited_until`.
- **Produce:**
  - `FIELDS` con las columnas `puesto` e `imagenes_gemini` al final;
  - `MetricsLog.append(task, status, result, conv, finished_at, images: int = 0)`;
  - `LimitLog(path).append(slot: str, engine: str, detected: float, until: float, task_key: str, message: str)`;
  - `CanvasClient.count_tool_calls(conversation_id: str, needle: str) -> int`;
  - `Config.limits_path: Path`, por defecto junto a `metrics.csv` (`limits.csv`).

- [ ] **Paso 1: escribir los tests que fallan**

En `dispatcher/tests/test_metrics.py`:
```python
def test_old_header_is_upgraded_without_misaligning_rows(tmp_path):
    p = tmp_path / "metrics.csv"
    old = ",".join(FIELDS[:-2])
    p.write_text(old + "\nqr,1,issue,dev,codex,label,a,b,1.0,finished,pr_abierto,0,0,0,0.0000,c1\n")
    MetricsLog(p).append(active_task(), "finished", "pr_abierto", None, 100.0, images=2)
    rows = MetricsLog(p).read()
    assert rows[0]["conversacion"] == "c1" and rows[0]["puesto"] == ""
    assert rows[1]["puesto"] == "codex-senior" and rows[1]["imagenes_gemini"] == "2"


def test_limit_log_appends(tmp_path):
    log = LimitLog(tmp_path / "limits.csv")
    log.append("codex-senior", "codex", 10.0, 20.0, "qr#1", "x" * 500)
    [row] = log.read()
    assert row["puesto"] == "codex-senior" and len(row["mensaje"]) == 200
```
(`active_task()` es un helper local que devuelve un `ActiveTask("qr", 1, "issue", "dev", "codex", "label", "c2", 0.0, "/w", slot="codex-senior")`; importar `FIELDS`, `LimitLog` y `MetricsLog`).

En `dispatcher/tests/test_canvas.py`:
```python
@respx.mock
def test_count_tool_calls_pages_and_counts_distinct_completed_calls(canvas):
    route("GET", f"/api/conversations/{ID1}/events/search").side_effect = [
        httpx.Response(200, json={"items": [
            {"kind": "ACPToolCallEvent", "title": "mcp__image__generate_image", "tool_call_id": "a", "status": "in_progress", "is_error": False},
            {"kind": "ACPToolCallEvent", "title": "mcp__image__generate_image", "tool_call_id": "a", "status": "completed", "is_error": False},
        ], "next_page_id": "p2"}),
        httpx.Response(200, json={"items": [
            {"kind": "ACPToolCallEvent", "title": "mcp.image.generate_image", "tool_call_id": "b", "status": "completed", "is_error": False},
            {"kind": "ACPToolCallEvent", "title": "mcp__image__generate_image", "tool_call_id": "c", "status": "completed", "is_error": True},
            {"kind": "MessageEvent", "title": "generate_image", "tool_call_id": "d", "status": "completed"},
        ], "next_page_id": None}),
    ]
    assert canvas.count_tool_calls(ID1, "generate_image") == 2
```
(con `import httpx` si no está).

- [ ] **Paso 2: correr y verificar que fallan**

Run: `uv run --with pytest --with respx python -m pytest -q tests/test_metrics.py tests/test_canvas.py`
Esperado: FALLAN por `LimitLog`, `count_tool_calls` y las columnas.

- [ ] **Paso 3: implementar**

En `metrics.py`:
```python
FIELDS = [
    "repo", "numero", "tipo", "rol", "motor", "disparador", "inicio", "fin", "duracion_min",
    "estado_final", "resultado", "tokens_entrada", "tokens_salida", "tokens_cache",
    "costo_estimado_usd", "conversacion", "puesto", "imagenes_gemini",
]
LIMIT_FIELDS = ["puesto", "motor", "detectado", "hasta", "tarea", "mensaje"]


def _ensure_header(path: Path, fields: list[str]) -> bool:
    """True si el archivo está vacío o no existe. Si tiene un encabezado viejo, lo reescribe con las columnas nuevas."""
    if not path.exists() or path.stat().st_size == 0:
        return True
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames == fields:
            return False
        rows = list(reader)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({f: row.get(f, "") for f in fields})
    tmp.replace(path)
    return False
```
En `MetricsLog.append`, sumar el parámetro `images: int = 0`, reemplazar el cálculo de `new_file` por `new_file = _ensure_header(self.path, FIELDS)` (después del `mkdir`) y agregar `"puesto": task.slot, "imagenes_gemini": images` al `writerow`. Crear:
```python
class LimitLog:
    def __init__(self, path: Path):
        self.path = path

    def append(self, slot: str, engine: str, detected: float, until: float, task_key: str, message: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = _ensure_header(self.path, LIMIT_FIELDS)
        with self.path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=LIMIT_FIELDS)
            if new_file:
                writer.writeheader()
            writer.writerow({"puesto": slot, "motor": engine, "detectado": iso(detected), "hasta": iso(until),
                             "tarea": task_key, "mensaje": message[:200]})

    def read(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        with self.path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
```
En `canvas.py`, dentro de `CanvasClient`:
```python
    def count_tool_calls(self, conversation_id: str, needle: str) -> int:
        """Llamadas a herramientas terminadas sin error cuyo nombre contiene `needle` (p. ej. generate_image)."""
        seen: set[str] = set()
        page: str | None = None
        while True:
            params: dict[str, Any] = {"limit": 100}
            if page:
                params["page_id"] = page
            resp = self.http.get(f"/api/conversations/{conversation_id}/events/search", params=params)
            resp.raise_for_status()
            data = resp.json()
            for e in data.get("items", []):
                if (e.get("kind") == "ACPToolCallEvent" and needle in (e.get("title") or "")
                        and e.get("status") == "completed" and not e.get("is_error")):
                    seen.add(e.get("tool_call_id") or e.get("id", ""))
            page = data.get("next_page_id")
            if not page:
                return len(seen)
```
En `config.py`, sumar `limits_path: Path | None = None`, y en `from_env`, `limits_path=Path(env.get("LIMITS_PATH", "/pilot/limits.csv"))`.

En `runner.py`:
- en `__init__`, sumar el parámetro `limit_log=None` y guardarlo en `self.limit_log`;
- en `_finish`, antes de `self.metrics.append`:
```python
        images = 0
        if a.conv is not None:
            try:
                images = self.canvas.count_tool_calls(task.conversation_id, "generate_image")
            except Exception:
                log.warning("No pude contar las imágenes de %s", task.conversation_id)
        if outcome.limited_until is not None and self.limit_log is not None:
            try:
                self.limit_log.append(task.slot or task.engine, task.engine, now, outcome.limited_until, task.key, final)
            except Exception:
                log.exception("No pude registrar el corte de %s", task.key)
```
y pasar `images=images` a `self.metrics.append`. En `__main__.py`, donde se construye el `Dispatcher`, pasar `limit_log=LimitLog(cfg.limits_path)` si `cfg.limits_path` no es `None`. En `fakes.py`, sumar a `FakeCanvas` un `count_tool_calls(self, conversation_id, needle): return 0`.

- [ ] **Paso 4: correr toda la suite**

Run: `uv run --with pytest --with respx python -m pytest -q`
Esperado: PASAN todos.

- [ ] **Paso 5: commit**

```bash
git add dispatcher/src/dispatcher/ dispatcher/tests/
git commit -m "feat(dispatcher): métricas por puesto, registro de cortes e imágenes de Gemini"
```

---

### Tarea 8: agregaciones y reglas de decisión

**Archivos:**
- Crear: `dispatcher/src/dispatcher/team_report.py`
- Test: `dispatcher/tests/test_team_report.py`

**Interfaces:**
- **Consume:** las filas de `MetricsLog.read()` y `LimitLog.read()`, y `Config.slots`, `slot_costs` y `gemini_image_usd`.
- **Produce** (lo va a usar la fase 5b):
  - `slot_stats(metrics_rows, limit_rows, slots, costs, image_usd, now, window_s) -> dict[str, SlotStats]`. `SlotStats` es un dataclass con `tasks: int`, `minutes: float`, `utilization: float` (de 0 a 1), `exhausted_hours: float`, `limit_hits: int`, `rework_per_issue: float` y `cost_usd: float`;
  - `decision_alerts(limit_rows, metrics_rows, slots, now) -> list[str]`.

- [ ] **Paso 1: escribir los tests que fallan**

```python
# dispatcher/tests/test_team_report.py
from dispatcher.metrics import iso
from dispatcher.models import Slot
from dispatcher.team_report import decision_alerts, slot_stats

DAY = 86400.0
NOW = 1_800_000_000.0
SLOTS = (Slot("claude-senior", "claude", "senior"), Slot("codex-senior", "codex", "senior"))


def m(slot, rol, numero, start, minutes, imgs=0, repo="nikito"):
    return {"repo": repo, "numero": str(numero), "rol": rol, "puesto": slot, "inicio": iso(start),
            "duracion_min": str(minutes), "imagenes_gemini": str(imgs), "motor": slot.split("-")[0]}


def lim(slot, detected, hours):
    return {"puesto": slot, "detectado": iso(detected), "hasta": iso(detected + hours * 3600)}


def test_slot_stats_counts_minutes_rework_cost_and_exhaustion():
    rows = [m("codex-senior", "dev", 3, NOW - 3600, 30), m("codex-senior", "fix", 3, NOW - 1800, 10),
            m("codex-senior", "qa", 3, NOW - 900, 5, imgs=2), m("claude-senior", "dev", 4, NOW - 10 * DAY, 60)]
    stats = slot_stats(rows, [lim("codex-senior", NOW - 7200, 1)], SLOTS, {"codex-senior": 300.0}, 0.04, NOW, DAY)
    s = stats["codex-senior"]
    assert (s.tasks, s.minutes, s.limit_hits) == (3, 45.0, 1)
    assert round(s.utilization, 3) == round(45 / 1440, 3)
    assert s.exhausted_hours == 1.0
    assert s.rework_per_issue == 2.0  # fix + qa sobre un issue
    assert round(s.cost_usd, 2) == round(300 / 30 + 2 * 0.04, 2)  # fijo mensual prorrateado a 1 día + imágenes
    assert stats["claude-senior"].tasks == 0


def test_alert_when_slot_exhausted_over_2h_on_3_of_last_5_days():
    limits = [lim("codex-senior", NOW - d * DAY - 4 * 3600, 3) for d in (0, 1, 3)]
    alerts = decision_alerts(limits, [], SLOTS, NOW)
    assert any("codex-senior" in a and "subir" in a for a in alerts)


def test_alert_when_slot_under_20_percent_in_7_days():
    alerts = decision_alerts([], [m("claude-senior", "dev", 1, NOW - DAY, 60)], SLOTS, NOW)
    assert any("claude-senior" in a and "bajar" in a for a in alerts)


def test_alert_on_high_rework():
    rows = [m("codex-senior", r, 1, NOW - 3600, 5) for r in ("dev", "fix", "qa", "fix", "qa", "fix")]
    rows += [m("codex-senior", "dev", 2, NOW - 3600, 600)]
    assert any("retrabajo" in a for a in decision_alerts([], rows, SLOTS, NOW))
```

- [ ] **Paso 2: correr y verificar que fallan**

Run: `uv run --with pytest --with respx python -m pytest -q tests/test_team_report.py`
Esperado: FALLA con `ModuleNotFoundError`.

- [ ] **Paso 3: implementar**

```python
# dispatcher/src/dispatcher/team_report.py
"""Consumo por puesto y reglas de decisión del presupuesto (spec fase 5a, secciones 6 y 7). Funciones puras."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from .models import Slot

DAY = 86400.0
REWORK_ROLES = ("fix", "qa")


@dataclass(frozen=True)
class SlotStats:
    tasks: int
    minutes: float
    utilization: float
    exhausted_hours: float
    limit_hits: int
    rework_per_issue: float
    cost_usd: float


def _ts(text: str) -> float:
    return datetime.fromisoformat(text).timestamp()


def _exhausted_seconds(limit_rows: Iterable[Mapping[str, str]], slot: str, start: float, end: float) -> tuple[float, int]:
    total, hits = 0.0, 0
    for r in limit_rows:
        if r.get("puesto") != slot:
            continue
        a, b = _ts(r["detectado"]), _ts(r["hasta"])
        overlap = min(b, end) - max(a, start)
        if overlap > 0:
            total += overlap
        if start <= a < end:
            hits += 1
    return total, hits


def _rework(rows: list[Mapping[str, str]]) -> float:
    per_issue: dict[tuple[str, str], int] = defaultdict(int)
    for r in rows:
        per_issue[(r["repo"], r["numero"])] += r["rol"] in REWORK_ROLES
    return sum(per_issue.values()) / len(per_issue) if per_issue else 0.0


def slot_stats(metrics_rows, limit_rows, slots: Iterable[Slot], costs: Mapping[str, float],
               image_usd: float, now: float, window_s: float) -> dict[str, SlotStats]:
    start = now - window_s
    limit_rows = list(limit_rows)
    recent = [r for r in metrics_rows if r.get("inicio") and _ts(r["inicio"]) >= start]
    out: dict[str, SlotStats] = {}
    for slot in slots:
        rows = [r for r in recent if r.get("puesto") == slot.name]
        minutes = sum(float(r["duracion_min"] or 0) for r in rows)
        exhausted, hits = _exhausted_seconds(limit_rows, slot.name, start, now)
        images = sum(int(r.get("imagenes_gemini") or 0) for r in rows)
        cost = costs.get(slot.name, 0.0) * (window_s / (30 * DAY)) + images * image_usd
        out[slot.name] = SlotStats(len(rows), minutes, minutes * 60 / window_s, exhausted / 3600, hits, _rework(rows), cost)
    return out


def decision_alerts(limit_rows, metrics_rows, slots: Iterable[Slot], now: float) -> list[str]:
    alerts: list[str] = []
    limit_rows, metrics_rows = list(limit_rows), list(metrics_rows)
    for slot in slots:
        bad_days = sum(
            1 for d in range(5)
            if _exhausted_seconds(limit_rows, slot.name, now - (d + 1) * DAY, now - d * DAY)[0] > 2 * 3600
        )
        if bad_days >= 3:
            alerts.append(f"{slot.name}: sin cupo más de 2 h en {bad_days} de los últimos 5 días → subir de nivel o sumar un puesto")
        week = slot_stats(metrics_rows, limit_rows, [slot], {}, 0.0, now, 7 * DAY)[slot.name]
        if week.utilization < 0.20:
            alerts.append(f"{slot.name}: {week.utilization:.0%} de uso en 7 días → evaluar bajar de nivel")
    week_rows = [r for r in metrics_rows if r.get("inicio") and _ts(r["inicio"]) >= now - 7 * DAY]
    if _rework(week_rows) > 2:
        alerts.append(f"retrabajo alto: {_rework(week_rows):.1f} rondas de fix y QA por issue en 7 días → partir las tareas en issues más chicos")
    return alerts
```

- [ ] **Paso 4: correr y verificar que pasan**

Run: `uv run --with pytest --with respx python -m pytest -q`
Esperado: PASAN todos.

- [ ] **Paso 5: commit**

```bash
git add dispatcher/src/dispatcher/team_report.py dispatcher/tests/test_team_report.py
git commit -m "feat(dispatcher): consumo por puesto y reglas de decisión de presupuesto"
```

---

### Tarea 9: etiquetas, documentación y ajuste del spec

**Archivos:**
- Modificar: `github/labels.txt`
- Modificar: `README.md` (secciones "Cómo funciona" y "MCP para los agentes", y una sección nueva "Puestos del equipo")
- Modificar: `docs/nuevo-proyecto.md` (paso 5, etiquetas de tamaño y tipo)
- Modificar: `docs/superpowers/specs/2026-10-12-fase-5a-equipo-por-puestos-design.md` (5.2, punto 3)
- Modificar: `.env.example`, si existe en el repo (o la sección "Credenciales" del README)

- [ ] **Paso 1: sumar las etiquetas a `github/labels.txt`**

Agregar con el formato del archivo (`nombre|color|descripción`):
```
size:S|C2E0C6|Tarea chica: pocas horas, un archivo o dos
size:M|FEF2C0|Tarea mediana (valor por defecto)
size:L|F9D0C4|Tarea grande: la toma Claude senior; preferir partirla
kind:architecture|5319E7|Decisiones de diseño técnico: la toma Claude senior
needs:images|BFD4F2|La tarea genera imágenes (Codex primero, Gemini de respaldo)
engine:gemini|1D76DB|Forzar el motor Gemini
```

- [ ] **Paso 2: documentar los puestos en el README**

Sección nueva "Puestos del equipo" con:
- la tabla de puestos de la sección 2 del spec;
- cómo configurar `SLOTS` y `SLOT_COST_<PUESTO>` en `.env`;
- la tabla de asignación (4.1);
- la prioridad (4.2);
- qué pasa con un límite de uso (5.2);
- dónde quedan `metrics.csv` (con `puesto` e `imagenes_gemini`) y `limits.csv`.

En "Cómo funciona", reemplazar "una tarea por motor" por "una tarea por puesto".

- [ ] **Paso 3: ajustar la guía y el spec**

- En `docs/nuevo-proyecto.md`, paso 5: "Poner `size:S`, `size:M` o `size:L` a cada issue, `kind:architecture` a las decisiones técnicas y `needs:images` a las tareas con imágenes. `engine:*` solo para forzar."
- En el spec, sección 5.2, punto 3, cambiar el texto del comentario por: "un solo comentario: '`<puesto>` se quedó sin cupo (hasta las HH:MM UTC); la tarea vuelve a la fila'", porque el mensaje queda genérico.

- [ ] **Paso 4: verificar que no quedaron referencias viejas**

Run: `grep -rn "QA_ENGINE\|DOCS_ENGINE\|DEFAULT_DEV_ENGINE\|una tarea por motor" README.md docs/*.md docker-compose.yml`
Esperado: sin resultados, o solo menciones históricas en `docs/bitacora.md`.

- [ ] **Paso 5: commit**

```bash
git add github/labels.txt README.md docs/nuevo-proyecto.md docs/superpowers/specs/2026-10-12-fase-5a-equipo-por-puestos-design.md
git commit -m "docs: puestos del equipo, etiquetas de tamaño y tipo, y respaldo por límite"
```

---

### Tarea 10: despliegue en la mini-PC (operativa: Claude Code con Eduardo)

**Archivos:**
- Modificar: `/opt/ai-dev-team/.env` en la mini-PC (nunca se commitea)
- Modificar: `docs/bitacora.md`

- [ ] **Paso 1: credenciales nuevas, cargadas por Eduardo por SSH**

- **Claude Max 5x:** `docker compose exec canvas claude` → `/login` con eduardo.jimenez@falconsoft.cl, en el volumen de `~/.claude`.
- **Codex Pro:** reemplazar `CODEX_AUTH_JSON` en `.env` por el `auth.json` de servicios@falconsoft.cl y borrar el volumen `ai-dev-team_codex-home` para forzar el login nuevo. Verificar con `docker compose exec canvas codex login status`, o con una conversación chica.
- **Gemini:** el login de la tarea 1, y `GEMINI_API_KEY` con la key nueva paga, si cambia.

- [ ] **Paso 2: configurar los puestos**

En `/opt/ai-dev-team/.env` (los costos son referencias del plan; Eduardo los confirma):
```
SLOTS=claude-senior:claude:senior,codex-senior:codex:senior,gemini:gemini:senior
SLOT_COST_CLAUDE_SENIOR=100
SLOT_COST_CODEX_SENIOR=200
SLOT_COST_GEMINI=20
LIMIT_TZ=America/Argentina/Buenos_Aires
GEMINI_IMAGE_USD=0.04
```
Borrar `QA_ENGINE`, `DOCS_ENGINE` y `DEFAULT_DEV_ENGINE` si están. Si la tarea 1 falló, dejar `gemini` fuera de `SLOTS`.

- [ ] **Paso 3: desplegar sin tareas activas**

Run:
```bash
cd /opt/ai-dev-team
sudo python3 -c "import json;print(json.load(open('/var/lib/docker/volumes/ai-dev-team_dispatcher-state/_data/state.json')).get('active',{}))"   # tiene que dar {}
sudo -u aidev git pull
docker compose up -d --no-deps --build canvas dispatcher
for r in agent-playground qr-generator ai-dev-team nikito; do scripts/sync-labels.sh maxiar-org/$r; done
```
Esperado: los contenedores `Up` y las etiquetas nuevas en los cuatro repos.

- [ ] **Paso 4: pruebas en vivo**

1. **Agotamiento simulado:** con el dispatcher detenido, cargar en `state.json` `"slot_exhausted_until": {"claude-senior": <ahora + 600>}` y arrancarlo. Poner `agent:review` en un PR de prueba en `agent-playground` con `engine:codex`. Esperado: la review la toma `gemini`, el respaldo, y no `claude-senior`.
2. **Un issue chico de punta a punta:** un issue `size:S` en `agent-playground` recorre dev (`codex-senior`), review (`claude-senior`), QA (`gemini`) y te llega el pedido de review. En `metrics.csv` quedan las tres filas con su `puesto`.

- [ ] **Paso 5: bitácora y cierre**

Entrada "Fase 5a desplegada" en `docs/bitacora.md`, con:
- los puestos activos y las cuentas, sin datos sensibles;
- el resultado de las pruebas;
- qué quedó pendiente (los semi senior y la fase 5b).

```bash
git add docs/bitacora.md && git commit -m "docs(bitácora): fase 5a desplegada"
```
