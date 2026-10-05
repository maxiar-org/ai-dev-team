# Fase 2: roles QA y Docs, plan de implementación

> **Para agentes que ejecuten este plan:** SUB-SKILL REQUERIDA: usar superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans para implementarlo tarea por tarea. Los pasos usan casillas (`- [ ]`) para seguir el avance.

**Objetivo:** sumar al dispatcher los roles QA (prueba de comportamiento con Playwright entre el reviewer y Eduardo) y Docs (sitio Starlight disparado con `agent:docs`), y tratar `ai-dev-team` como repo de solo documentación.

**Arquitectura:** se extiende la máquina de estados existente, que tiene funciones puras (`decide`, `outcome_for`) y un runner que ejecuta. Después de un `VEREDICTO: APROBADO`, el PR pasa a `agent:qa` en lugar de pedir review a Eduardo. `QA: OK` o `N/A` le pide review; `QA: FALLA` lo manda a `agent:fix`. Los roles se definen con plantillas Markdown en `roles/`.

**Stack:** Python 3.12, pytest, respx, Docker Compose, OpenHands Canvas (ACP), GitHub CLI y Starlight (Astro), que generan los propios agentes.

**Spec:** `docs/superpowers/specs/2026-10-05-fase-2-qa-docs-design.md`

## Restricciones globales

- **Labels nuevos:** `agent:qa` (lo pone el dispatcher) y `agent:docs` (lo pone Eduardo en un issue).
- **Variables nuevas:** `QA_ENGINE` (por defecto `codex`), `DOCS_ENGINE` (por defecto `claude`), `DOCS_ONLY_REPOS` (lista separada por comas, por defecto vacía).
- **Veredicto de QA:** `QA: OK`, `QA: FALLA` o `QA: N/A`. Se toma el último y se tolera markdown (`**`).
- **Rondas:** máximo 2 de QA por PR (contador `qa_rounds`), independiente de las 2 de review.
- **Evidencia de QA:** rama huérfana `qa-evidence`, carpeta `pr-<n>/ronda-<k>/`. Los enlaces usan `raw.githubusercontent.com`.
- **Repos de solo documentación:** `agent:dev` no arranca y se avisa una sola vez. Un comentario `@openhands` en un issue de esos repos dispara `docs`, no `dev`.
- **Código y textos:** el código y los identificadores en inglés; los textos para Eduardo en español.

## Foco de revisión

1. **Un PR con `agent:qa` y `engine:codex`:** el QA usa `QA_ENGINE`, no el motor del PR, y el reviewer sigue usando el motor contrario al del dev. Test: `test_qa_uses_configured_engine_not_pr_engine` (tarea 3).
2. **Un `QA: FALLA` tras 2 rondas de QA:** debe escalar a `needs:human` y no seguir en bucle. Test: `test_qa_failure_after_max_rounds_escalates` (tarea 2).
3. **Un reviewer que escribe "QA: OK" en su comentario:** su veredicto se sigue leyendo solo como `VEREDICTO`, y un QA que escribe "VEREDICTO: APROBADO" sin `QA:` no cuenta como OK. Test: `test_qa_without_qa_verdict_escalates` (tarea 2).
4. **Un comentario `@openhands` de Eduardo en un issue de un repo de solo documentación:** dispara `docs`, nunca `dev`. Test: `test_comment_in_docs_only_repo_triggers_docs` (tarea 3).
5. **Un issue con `agent:docs` y `Depende de #N` abierto:** espera igual que `dev`. Test: `test_docs_issue_waits_for_dependency` (tarea 3).

---

### Tarea 1: Configuración y modelos

**Archivos:**
- Modificar: `dispatcher/src/dispatcher/config.py`, `dispatcher/src/dispatcher/models.py`, `dispatcher/src/dispatcher/state.py`
- Tests: `dispatcher/tests/test_config.py`, `dispatcher/tests/test_state.py`

**Interfaces:**
- Produce:
  - `Config.qa_engine: str`, `Config.docs_engine: str`, `Config.docs_only_repos: tuple[str, ...]`
  - `Role = Literal["dev", "review", "fix", "qa", "docs"]`
  - `LABEL_QA = "agent:qa"`, `LABEL_DOCS = "agent:docs"`
  - `DocsOnlyNotice(item: Item)` (acción)
  - `State.qa_rounds: dict[str, int]`, `State.docs_only_notified: set[str]`

- [ ] **Paso 1: Tests que fallan.** Agregar a `dispatcher/tests/test_config.py`:

```python
def test_phase2_engines_and_docs_only_repos():
    cfg = Config.from_env(BASE)
    assert (cfg.qa_engine, cfg.docs_engine, cfg.docs_only_repos) == ("codex", "claude", ())
    cfg = Config.from_env({**BASE, "QA_ENGINE": "claude", "DOCS_ENGINE": "codex", "DOCS_ONLY_REPOS": "ai-dev-team, x"})
    assert (cfg.qa_engine, cfg.docs_engine, cfg.docs_only_repos) == ("claude", "codex", ("ai-dev-team", "x"))
    with pytest.raises(ConfigError, match="QA_ENGINE"):
        Config.from_env({**BASE, "QA_ENGINE": "gemini"})
```

En `dispatcher/tests/test_state.py`, en `test_roundtrip_is_lossless_and_atomic`, agregar al `State(...)` los argumentos `qa_rounds={"qr#12": 1}` y `docs_only_notified={"ai-dev-team#3"}`.

- [ ] **Paso 2:** ejecutar `cd dispatcher && uv run pytest tests/test_config.py tests/test_state.py -q`. Resultado esperado: FAIL (`AttributeError: qa_engine` o `TypeError: unexpected keyword 'qa_rounds'`).

- [ ] **Paso 3: Implementar.**

  **`config.py`:** después de `project_number: int | None = None`, agregar:

```python
    qa_engine: str = "codex"
    docs_engine: str = "claude"
    docs_only_repos: tuple[str, ...] = ()
```

  Dentro de `from_env`, reemplazar la validación de `engine` por un helper y usarlo para los tres motores:

```python
        def engine_var(name: str, default: str) -> str:
            value = env.get(name, "").strip() or default
            if value not in ENGINES:
                raise ConfigError(f"{name} debe ser uno de {ENGINES}, no {value!r}")
            return value

        engine = engine_var("DEFAULT_DEV_ENGINE", "codex")
```

  Y en el `return cls(...)`, agregar:

```python
            qa_engine=engine_var("QA_ENGINE", "codex"),
            docs_engine=engine_var("DOCS_ENGINE", "claude"),
            docs_only_repos=tuple(r.strip() for r in env.get("DOCS_ONLY_REPOS", "").split(",") if r.strip()),
```

  **`models.py`:** cambiar `Role` a `Literal["dev", "review", "fix", "qa", "docs"]`. Debajo de `LABEL_HUMAN`, agregar `LABEL_QA = "agent:qa"` y `LABEL_DOCS = "agent:docs"`. Antes de `Action = Union[...]`, agregar:

```python
@dataclass(frozen=True)
class DocsOnlyNotice:
    """agent:dev en un repo de solo documentación: no arranca y se avisa una vez."""

    item: Item
```

  E incluir `DocsOnlyNotice` en `Action`.

  **`state.py`:** en `State`, agregar `qa_rounds: dict[str, int] = field(default_factory=dict)` y `docs_only_notified: set[str] = field(default_factory=set)`. En `load`, agregar `qa_rounds=dict(data.get("qa_rounds", {}))` y `docs_only_notified=set(data.get("docs_only_notified", []))`. En `save`, agregar `"qa_rounds": state.qa_rounds` y `"docs_only_notified": sorted(state.docs_only_notified)`.

- [ ] **Paso 4:** ejecutar `cd dispatcher && uv run pytest -q`. Resultado esperado: todo pasa.

- [ ] **Paso 5:** commit:

```bash
git commit -am "feat(dispatcher): configuración y modelos de los roles QA y Docs"
```

---

### Tarea 2: Resultado de las tareas QA y Docs (`outcomes`)

**Archivos:**
- Modificar: `dispatcher/src/dispatcher/outcomes.py`
- Tests: `dispatcher/tests/test_outcomes.py`

**Interfaces:**
- Consume: `LABEL_QA` y `LABEL_DOCS` (tarea 1).
- Produce:
  - `parse_qa_verdict(text) -> str | None`, que devuelve `"OK"`, `"FALLA"`, `"N/A"` o `None`
  - `Outcome(result, ops, review_rounds, qa_rounds=0)`
  - `outcome_for(task, status, final_response, current_labels, pr, rounds, max_rounds, qa_rounds=0) -> Outcome`

- [ ] **Paso 1: Tests que fallan.** En `dispatcher/tests/test_outcomes.py`, **reemplazar** `test_review_approved_requests_human_review` por:

```python
def test_review_approved_goes_to_qa():
    out = outcome_for(task("review", "pr", 7, "claude"), "finished", "Todo bien.\nVEREDICTO: APROBADO", frozenset(), None, 0, 2)
    assert (out.result, out.ops[-1]) == ("aprobado", AddLabels(7, ("agent:qa",)))
```

Y agregar:

```python
@pytest.mark.parametrize(
    "text,expected",
    [("QA: OK", "OK"), ("**QA: FALLA**", "FALLA"), ("QA: n/a", "N/A"), ("QA: FALLA\n...\nQA: OK", "OK"), ("VEREDICTO: APROBADO", None)],
)
def test_parse_qa_verdict(text, expected):
    assert parse_qa_verdict(text) == expected


@pytest.mark.parametrize("verdict,result", [("OK", "qa_ok"), ("N/A", "qa_na")])
def test_qa_ok_or_na_requests_human_review(verdict, result):
    out = outcome_for(task("qa", "pr", 7, "codex"), "finished", f"Probé todo.\nQA: {verdict}", frozenset(), None, 0, 2)
    assert (out.result, out.ops[-1]) == (result, RequestReview(7))
    assert RemoveLabel(7, "agent:qa") in out.ops


def test_qa_failure_sends_to_fix_and_counts_qa_round():
    out = outcome_for(task("qa", "pr", 7, "codex"), "finished", "QA: FALLA", frozenset(), None, 1, 2, qa_rounds=0)
    assert (out.result, out.review_rounds, out.qa_rounds, out.ops[-1]) == ("qa_falla", 1, 1, AddLabels(7, ("agent:fix",)))


def test_qa_failure_after_max_rounds_escalates():
    out = outcome_for(task("qa", "pr", 7, "codex"), "finished", "QA: FALLA", frozenset(), None, 0, 2, qa_rounds=2)
    assert (out.result, out.qa_rounds) == ("max_rondas_qa", 3)
    assert AddLabels(7, ("needs:human",)) in out.ops


def test_qa_without_qa_verdict_escalates():
    out = outcome_for(task("qa", "pr", 7, "codex"), "finished", "VEREDICTO: APROBADO", frozenset(), None, 0, 2)
    assert out.result == "sin_resultado" and AddLabels(7, ("needs:human",)) in out.ops


def test_docs_with_pr_goes_to_review_like_dev():
    out = outcome_for(task("docs", "issue", 3, "claude"), "finished", "", frozenset(), pr_item(), 0, 2)
    assert out.result == "pr_abierto"
    assert out.ops == (
        RemoveLabel(3, "agent:working"),
        RemoveLabel(3, "agent:docs"),
        AddLabels(7, ("agent:review", "engine:claude")),
    )


def test_review_rounds_and_qa_rounds_are_preserved_when_unchanged():
    out = outcome_for(task("fix", "pr", 7), "finished", "", frozenset(), None, 1, 2, qa_rounds=1)
    assert (out.review_rounds, out.qa_rounds) == (1, 1)
```

Actualizar el import: `from dispatcher.outcomes import find_pr_for_issue, outcome_for, parse_qa_verdict, parse_verdict`.

- [ ] **Paso 2:** ejecutar `cd dispatcher && uv run pytest tests/test_outcomes.py -q`. Resultado esperado: FAIL (`ImportError: parse_qa_verdict`).

- [ ] **Paso 3: Implementar.** En `outcomes.py`:
  - Importar también `LABEL_DOCS` y `LABEL_QA`.
  - Debajo de `VERDICT_RE`, agregar:

```python
QA_VERDICT_RE = re.compile(r"QA:\s*\**\s*(OK|FALLA|N/A)", re.IGNORECASE)
```

  - Cambiar `TRIGGER_LABELS` por:

```python
TRIGGER_LABELS = {"dev": LABEL_DEV, "review": LABEL_REVIEW, "fix": LABEL_FIX, "qa": LABEL_QA, "docs": LABEL_DOCS}
```

  - Cambiar `Outcome` por:

```python
@dataclass(frozen=True)
class Outcome:
    result: str
    ops: tuple[GitHubOp, ...]
    review_rounds: int
    qa_rounds: int = 0
```

  - Agregar debajo de `parse_verdict`:

```python
def parse_qa_verdict(text: str) -> str | None:
    matches = QA_VERDICT_RE.findall(text or "")
    return matches[-1].upper() if matches else None
```

  - Reemplazar `outcome_for` completa por:

```python
def outcome_for(
    task: ActiveTask,
    status: str,
    final_response: str,
    current_labels: frozenset[str],
    pr: Item | None,
    rounds: int,
    max_rounds: int,
    qa_rounds: int = 0,
) -> Outcome:
    n = task.number
    # El label disparador se quita siempre: si quedara, la tarea se repetiría en bucle.
    ops: list[GitHubOp] = [RemoveLabel(n, LABEL_WORKING), RemoveLabel(n, TRIGGER_LABELS[task.role])]

    def done(result: str, review: int = rounds, qa: int = qa_rounds) -> Outcome:
        return Outcome(result, tuple(ops), review, qa)

    def escalate(result: str, message: str, review: int = rounds, qa: int = qa_rounds) -> Outcome:
        ops.extend([AddLabels(n, (LABEL_HUMAN,)), PostComment(n, message)])
        return done(result, review, qa)

    if status not in NORMAL_STATUSES:
        return escalate(
            "needs_human",
            f"⚠️ La tarea `{task.role}` con `{task.engine}` terminó con estado `{status}`. "
            f"Revisa la conversación `{task.conversation_id}` en Canvas.\n\n"
            f"Última respuesta del agente:\n\n{_quote(final_response)}",
        )

    if task.role in ("dev", "docs"):
        if pr is not None:
            ops.append(AddLabels(pr.number, (LABEL_REVIEW, f"engine:{task.engine}")))
            return done("pr_abierto")
        if LABEL_HUMAN in current_labels:
            return done("needs_human")
        return escalate(
            "sin_resultado",
            "El agente terminó sin abrir un PR ni pedir ayuda.\n\n"
            f"Última respuesta:\n\n{_quote(final_response)}",
        )

    if task.role == "review":
        verdict = parse_verdict(final_response)
        if verdict == "APROBADO":
            ops.append(AddLabels(n, (LABEL_QA,)))
            return done("aprobado")
        if verdict == "CAMBIOS":
            new_rounds = rounds + 1
            if new_rounds <= max_rounds:
                ops.append(AddLabels(n, (LABEL_FIX,)))
                return done("cambios", review=new_rounds)
            return escalate(
                "max_rondas",
                f"El reviewer volvió a pedir cambios y ya se hicieron {max_rounds} rondas "
                "automáticas. Necesito tu decisión: comenta con @openhands lo que debe hacer "
                "el dev, o mergea/cierra el PR.",
                review=new_rounds,
            )
        return escalate(
            "sin_resultado",
            "El reviewer terminó sin dejar `VEREDICTO: APROBADO` ni `VEREDICTO: CAMBIOS`.\n\n"
            f"Última respuesta:\n\n{_quote(final_response)}",
        )

    if task.role == "qa":
        verdict = parse_qa_verdict(final_response)
        if verdict in ("OK", "N/A"):
            ops.append(RequestReview(n))
            return done("qa_ok" if verdict == "OK" else "qa_na")
        if verdict == "FALLA":
            new_qa = qa_rounds + 1
            if new_qa <= max_rounds:
                ops.append(AddLabels(n, (LABEL_FIX,)))
                return done("qa_falla", qa=new_qa)
            return escalate(
                "max_rondas_qa",
                f"QA volvió a fallar y ya se hicieron {max_rounds} rondas automáticas de QA. "
                "Revisa las capturas del último comentario de QA y decide cómo seguir.",
                qa=new_qa,
            )
        return escalate(
            "sin_resultado",
            "QA terminó sin dejar `QA: OK`, `QA: FALLA` ni `QA: N/A`.\n\n"
            f"Última respuesta:\n\n{_quote(final_response)}",
        )

    # role == "fix"
    if LABEL_HUMAN in current_labels:
        return done("needs_human")
    # Tras una corrección por label o por conflicto vuelve a revisar el agente: una resolución de
    # conflictos puede descartar funcionalidad sin que el CI lo note. Si lo pidió Eduardo, le vuelve a él.
    ops.append(RequestReview(n) if task.trigger == "comment" else AddLabels(n, (LABEL_REVIEW,)))
    return done("fix_aplicado")
```

- [ ] **Paso 4:** ejecutar `cd dispatcher && uv run pytest tests/test_outcomes.py -q`. Resultado esperado: todo pasa.

- [ ] **Paso 5:** commit:

```bash
git commit -am "feat(dispatcher): resultados de QA y Docs; review aprobado pasa a QA"
```

---

### Tarea 3: Decisión (`decide`): candidatos de QA y Docs, y repos de solo documentación

**Archivos:**
- Modificar: `dispatcher/src/dispatcher/decide.py`
- Tests: `dispatcher/tests/test_decide.py`

**Interfaces:**
- Consume: `Config.qa_engine`, `docs_engine` y `docs_only_repos`; `LABEL_QA`, `LABEL_DOCS` y `DocsOnlyNotice`; `State.docs_only_notified` (tarea 1).

- [ ] **Paso 1: Tests que fallan.** Agregar a `dispatcher/tests/test_decide.py`. Agregar `DocsOnlyNotice` al import de `dispatcher.models`, y al principio del archivo `import dataclasses`.

```python
def test_issue_with_agent_docs_starts_docs_with_docs_engine(cfg):
    [start] = starts(decide([issue(1, "agent:docs")], [], {}, State(), cfg, NOW))
    assert (start.role, start.engine) == ("docs", "claude")


def test_qa_uses_configured_engine_not_pr_engine(cfg):
    [start] = starts(decide([pr(5, "agent:qa", "engine:codex")], [], {}, State(), cfg, NOW))
    assert (start.role, start.engine) == ("qa", "codex")
    cfg2 = dataclasses.replace(cfg, qa_engine="claude")
    [start] = starts(decide([pr(5, "agent:qa", "engine:codex")], [], {}, State(), cfg2, NOW))
    assert start.engine == "claude"


def test_agent_dev_in_docs_only_repo_does_not_start_and_notifies_once(cfg):
    cfg2 = dataclasses.replace(cfg, docs_only_repos=("qr",))
    i = issue(1, "agent:dev")
    assert decide([i], [], {}, State(), cfg2, NOW) == [DocsOnlyNotice(i)]
    assert decide([i], [], {}, State(docs_only_notified={"qr#1"}), cfg2, NOW) == []


def test_comment_in_docs_only_repo_triggers_docs(cfg):
    cfg2 = dataclasses.replace(cfg, docs_only_repos=("qr",))
    c = Comment(95, "qr", 1, "maxiar", "@openhands documentá esto")
    [start] = starts(decide([issue(1)], [c], {}, State(), cfg2, NOW))
    assert (start.role, start.engine) == ("docs", "claude")


def test_docs_issue_waits_for_dependency(cfg):
    blocked = Item("qr", 5, "issue", "Docs", "Depende de #4", frozenset({"agent:docs"}))
    assert starts(decide([blocked, issue(4)], [], {}, State(), cfg, NOW)) == []
```

- [ ] **Paso 2:** ejecutar `cd dispatcher && uv run pytest tests/test_decide.py -q`. Resultado esperado: FAIL.

- [ ] **Paso 3: Implementar.** En `decide.py`:
  - Importar `LABEL_DOCS`, `LABEL_QA` y `DocsOnlyNotice`.
  - En `_label_candidates`, reemplazar el bloque `if item.kind == "issue" and LABEL_DEV in labels: ... elif ... LABEL_REVIEW ...` por:

```python
        if item.kind == "issue" and LABEL_DOCS in labels:
            out.append(StartTask(item, "docs", engine_from_labels(labels, cfg.docs_engine), "label"))
        elif item.kind == "issue" and LABEL_DEV in labels:
            out.append(StartTask(item, "dev", dev_engine, "label"))
        elif item.kind == "pr" and LABEL_FIX in labels:
            out.append(StartTask(item, "fix", dev_engine, "label"))
        elif item.kind == "pr" and LABEL_REVIEW in labels:
            out.append(StartTask(item, "review", other_engine(dev_engine), "label"))
        elif item.kind == "pr" and LABEL_QA in labels:
            out.append(StartTask(item, "qa", cfg.qa_engine, "label"))
```

  - En `_comment_candidates`, reemplazar las dos líneas de `role` y `engine` por:

```python
        if item.kind == "pr":
            role, default_engine = "fix", cfg.default_dev_engine
        elif item.repo in cfg.docs_only_repos or LABEL_DOCS in item.labels:
            role, default_engine = "docs", cfg.docs_engine
        else:
            role, default_engine = "dev", cfg.default_dev_engine
        engine = engine_from_labels(item.labels, default_engine)
```

  - En `decide`, dentro del `for candidate in _label_candidates(items, cfg):`, como primeras líneas del cuerpo, agregar:

```python
        if candidate.role == "dev" and candidate.item.repo in cfg.docs_only_repos:
            if candidate.item.key not in state.docs_only_notified:
                actions.append(DocsOnlyNotice(candidate.item))
            continue
```

    Cambiar `if candidate.role == "dev":` (la línea de las dependencias) por `if candidate.role in ("dev", "docs"):`.

  - En el bloque de conflictos, cambiar `{LABEL_WORKING, LABEL_HUMAN, LABEL_REVIEW, LABEL_FIX}` por `{LABEL_WORKING, LABEL_HUMAN, LABEL_REVIEW, LABEL_FIX, LABEL_QA}`: un PR esperando QA no debe recibir un fix de conflictos en paralelo. Agregar el test:

```python
def test_pr_waiting_for_qa_is_not_fixed_for_conflicts(cfg):
    actions = decide([dirty_pr(11, "agent:qa")], [], {}, State(), cfg, NOW)
    assert [a for a in actions if isinstance(a, StartTask) and a.trigger == "conflict"] == []
```

- [ ] **Paso 4:** ejecutar `cd dispatcher && uv run pytest -q`. Resultado esperado: todo pasa, salvo los tests del runner que se ajustan en la tarea 4. Si fallan solo `test_github_failure_while_finishing_frees_the_engine` y `test_conflict_that_keeps_failing_escalates`, es lo esperado.

- [ ] **Paso 5:** commit:

```bash
git commit -am "feat(dispatcher): decidir tareas de QA y Docs y respetar repos de solo documentación"
```

---

### Tarea 4: Runner, prompts y roles

**Archivos:**
- Modificar: `dispatcher/src/dispatcher/runner.py`, `dispatcher/src/dispatcher/prompts.py`, `roles/dev.md`, `roles/reviewer.md`, `roles/fix.md`
- Crear: `roles/qa.md`, `roles/docs.md`
- Tests: `dispatcher/tests/test_runner.py`, `dispatcher/tests/test_prompts.py`

**Interfaces:**
- Consume: `outcome_for(..., qa_rounds=...)` y `Outcome.qa_rounds` (tarea 2), `DocsOnlyNotice` (tarea 1).

- [ ] **Paso 1: Tests que fallan.**

  En `dispatcher/tests/test_runner.py`:
  - **Reemplazar** el cuerpo de `test_github_failure_while_finishing_frees_the_engine` para que use QA:

```python
def test_github_failure_while_finishing_frees_the_engine(tmp_path, cfg):
    d, gh, cv, ws, clock = make(tmp_path, cfg)
    gh.add_item(Item(REPO, 7, "pr", "WA", "", frozenset({"agent:qa", "engine:codex"}), "agent/3-wa"))
    d.run_once()
    cv.status["conv1"] = "finished"
    cv.responses["conv1"] = "QA: OK"
    gh.fail_request_review = True
    d.run_once()
    assert StateStore(cfg.state_path).load().active == {}
    assert len(MetricsLog(cfg.metrics_path).read()) == 1
    assert "needs:human" in gh.labels(7)
```

  - En `test_conflict_that_keeps_failing_escalates`, cambiar `cv.responses[conv_id] = "VEREDICTO: APROBADO"` por `cv.responses[conv_id] = "VEREDICTO: APROBADO\nQA: OK"`.
  - Agregar:

```python
def test_review_then_qa_failure_then_fix_then_qa_ok(tmp_path, cfg):
    d, gh, cv, ws, clock = make(tmp_path, cfg)
    gh.add_item(Item(REPO, 7, "pr", "WA", "", frozenset({"agent:review", "engine:codex"}), "agent/3-wa"))
    script = ["VEREDICTO: APROBADO", "Falta el campo.\nQA: FALLA", "Corregido.", "VEREDICTO: APROBADO", "QA: OK"]
    for response in script:
        d.run_once()  # inicia la tarea siguiente
        conv_id = f"conv{len(cv.created)}"
        cv.status[conv_id] = "finished"
        cv.responses[conv_id] = response
        d.run_once()  # la cierra
    assert gh.review_requests == [(7, ("maxiar",))]
    assert StateStore(cfg.state_path).load().qa_rounds == {f"{REPO}#7": 1}
    assert len(cv.created) == 5


def test_docs_only_repo_notice_is_posted_once(tmp_path, cfg):
    import dataclasses

    cfg2 = dataclasses.replace(cfg, docs_only_repos=(REPO,))
    d, gh, cv, ws, clock = make(tmp_path, cfg2)
    gh.add_item(Item(REPO, 3, "issue", "Código", "", frozenset({"agent:dev"})))
    d.run_once()
    d.run_once()
    assert cv.created == []
    assert len(gh.posted) == 1 and "documentación" in gh.posted[0][1]
```

  En `dispatcher/tests/test_prompts.py`, agregar:

```python
def test_qa_prompt_has_verdicts_and_evidence_branch(cfg):
    item = Item("qr-generator", 7, "pr", "WA", "Closes #3", frozenset(), "agent/3-wa")
    text = build_prompt(cfg.roles_dir, "qa", item, "maxiar-org")
    assert "QA: OK" in text and "QA: FALLA" in text and "QA: N/A" in text
    assert "qa-evidence" in text and "agent/3-wa" in text and "{{" not in text


def test_docs_prompt_mentions_starlight_and_pages(cfg):
    item = Item("ai-dev-team", 4, "issue", "Sitio de docs", "Crear el sitio", frozenset())
    text = build_prompt(cfg.roles_dir, "docs", item, "maxiar-org")
    assert "Starlight" in text and "GitHub Pages" in text and "/ai-dev-team/" in text
    assert "agent/4-sitio-de-docs" in text and "{{" not in text
```

- [ ] **Paso 2:** ejecutar `cd dispatcher && uv run pytest -q`. Resultado esperado: FAIL (falta `qa.md`, falta el manejo de `DocsOnlyNotice` y de `qa_rounds`).

- [ ] **Paso 3: Implementar.**

  **`prompts.py`:**

```python
ROLE_FILES: dict[str, str] = {"dev": "dev.md", "review": "reviewer.md", "fix": "fix.md", "qa": "qa.md", "docs": "docs.md"}
```

  **`runner.py`:**
  - Importar `DocsOnlyNotice`.
  - En `_apply`, agregar la rama:

```python
        elif isinstance(action, DocsOnlyNotice):
            item = action.item
            self.github.comment(
                item.repo, item.number,
                "ℹ️ Este repo es de **solo documentación**: los agentes no cambian código acá, así que "
                "`agent:dev` no arranca. Si es una tarea de documentación, usá `agent:docs`.",
            )
            state.docs_only_notified.add(item.key)
```

  - En `_finish`, en la llamada a `outcome_for`, agregar `qa_rounds=state.qa_rounds.get(task.key, 0)`, y después de `state.review_rounds[task.key] = outcome.review_rounds`, agregar `state.qa_rounds[task.key] = outcome.qa_rounds`.

  **`roles/dev.md`:** en el paso 5, borrar la oración que empieza con "Si el cambio es visual y tienes herramientas de Playwright…".

  **`roles/reviewer.md`:** borrar el ítem que empieza con "- **UI:** si el proyecto tiene interfaz web…" y agregar en su lugar:

```markdown
   - **repos de solo documentación:** si `AGENTS.md` dice que el repo es de solo documentación, cualquier cambio fuera de `docs/` y de los archivos `.md` es **bloqueante**.

   No abras la app en el navegador: el comportamiento lo prueba el rol QA después de tu aprobación.
```

  **`roles/fix.md`:** en el paso 2, reemplazar "Lo que hay que corregir está en el último comentario del reviewer (el que tiene `VEREDICTO: CAMBIOS`) o en el pedido de arriba." por "Lo que hay que corregir está en el último comentario con `VEREDICTO: CAMBIOS` (reviewer) o con `QA: FALLA` (QA, con pasos y capturas), o en el pedido de arriba."

  **`roles/qa.md`** (nuevo):

````markdown
Eres el **QA** del AI Dev Team de `{{org}}`. El reviewer ya aprobó el código de este PR. Tu trabajo es probar el **comportamiento**: usar la app como la usaría la persona usuaria y confirmar que funciona. No revisas el código ni lo modificas.

## PR a probar

Repositorio `{{org}}/{{repo}}`, {{kind}} #{{number}}: **{{title}}** (rama `{{branch}}`)

{{body}}

## Cómo trabajar

1. Estás en una copia del repo con la rama `{{branch}}`. Lee `AGENTS.md`, sobre todo las secciones "Probar la UI" y los flujos principales.
2. Lee el issue vinculado y sus criterios de aceptación: `gh pr view {{number}} --repo {{org}}/{{repo}}`.
3. Si el PR no tiene cambios visibles para la persona usuaria (por ejemplo, solo documentación de texto o configuración), responde `QA: N/A` con una línea que explique por qué y termina.
4. Escribe un **plan de prueba numerado**: un paso por cada criterio de aceptación, más los flujos principales de `AGENTS.md` (regresión).
5. Compila y sirve la app como indica `AGENTS.md` y ejecuta el plan con las herramientas de Playwright. Toma una captura en cada paso relevante.
6. **Evidencia:** sube las capturas a la rama `qa-evidence` (huérfana; créala si no existe), en `pr-{{number}}/ronda-<n>/`, donde `<n>` es 1 más la cantidad de rondas anteriores que ya estén en esa carpeta:

   ```bash
   git fetch origin qa-evidence || true
   git worktree add /tmp/qa-evidence origin/qa-evidence 2>/dev/null || (git worktree add --detach /tmp/qa-evidence && git -C /tmp/qa-evidence checkout --orphan qa-evidence && git -C /tmp/qa-evidence rm -rf . >/dev/null 2>&1 || true)
   # copiá las capturas a /tmp/qa-evidence/pr-{{number}}/ronda-<n>/
   git -C /tmp/qa-evidence add -A && git -C /tmp/qa-evidence commit -m "QA PR #{{number}} ronda <n>" && git -C /tmp/qa-evidence push origin HEAD:qa-evidence
   ```

   Enlázalas con `https://raw.githubusercontent.com/{{org}}/{{repo}}/qa-evidence/pr-{{number}}/ronda-<n>/<archivo>.png`.
7. Publica **un solo** comentario en el PR (`gh pr comment {{number}} --repo {{org}}/{{repo}} --body-file <archivo>`) con: el plan, el resultado de cada paso (✅ o ❌) con su captura y, por cada falla, **pasos para reproducirla, resultado esperado y resultado obtenido**. Al final, una línea exacta:
   - `QA: OK` si todo funciona;
   - `QA: FALLA` si al menos un paso falla;
   - `QA: N/A` si no aplica (paso 3).

## Reglas

- No modifiques el código del PR ni hagas commits en la rama `{{branch}}`.
- No apruebes ni mergees el PR.
- Termina tu respuesta final repitiendo la misma línea `QA: ...`.
````

  **`roles/docs.md`** (nuevo):

````markdown
Eres el **documentador** del AI Dev Team de `{{org}}`. Escribes documentación clara para personas, en español rioplatense, con ejemplos concretos y diagramas Mermaid cuando ayudan a entender.

## Tarea

Repositorio `{{org}}/{{repo}}`, {{kind}} #{{number}}: **{{title}}**

{{body}}

### Instrucciones adicionales de Eduardo

{{instruction}}

## Cómo trabajar

1. Estás en una copia del repo. Lee `AGENTS.md` y el issue completo: `gh issue view {{number}} --repo {{org}}/{{repo}} --comments`.
2. Crea la rama `{{branch}}` (o continúa sobre ella si ya existe en origin).
3. La documentación vive en un sitio **Starlight** (Astro) dentro de `docs/`:
   - Si no existe, créalo: proyecto Astro con Starlight en `docs/`, interfaz en español, búsqueda y sidebar autogenerado desde `docs/src/content/docs/`. Configura `site: 'https://{{org}}.github.io'` y `base: '/{{repo}}/'`.
   - Agrega el workflow `.github/workflows/docs.yml`, que construye `docs/` y lo publica en **GitHub Pages** con `actions/upload-pages-artifact` y `actions/deploy-pages`, en cada push a `main` que toque `docs/`.
   - Si `docs/` ya tiene otros archivos (por ejemplo `docs/superpowers/` o documentos sueltos), no los borres ni los muevas. Enlázalos desde el sitio si son útiles para personas.
4. Verifica que el sitio compile (`npm ci && npm run build` en `docs/`) y que los enlaces internos funcionen.
5. Abre el PR con `Closes #{{number}}`, un resumen de las páginas creadas o cambiadas y una sección **Entregable visible** con la URL final del sitio (`https://{{org}}.github.io/{{repo}}/`) y cómo verlo localmente (`npm run preview`).

## Si te falta información

Comenta tus preguntas en el issue, agrega el label `needs:human` y termina.

## Reglas

- Solo cambias documentación: `docs/`, archivos `.md` y el workflow de deploy de docs. Nunca código de la aplicación ni del dispatcher.
- Nunca hagas push a la rama por defecto ni mergees PRs.
- Al terminar, responde con un resumen breve y el número del PR.
````

- [ ] **Paso 4:** ejecutar `cd dispatcher && uv run pytest -q`. Resultado esperado: todo pasa.

- [ ] **Paso 5:** commit:

```bash
git add -A dispatcher roles && git commit -m "feat: roles QA y Docs en el runner y sus plantillas; reviewer y dev sin navegador"
```

---

### Tarea 5: Despliegue y configuración de los repos

**Archivos:**
- Modificar: `docker-compose.yml`, `.env.example`, `.env`, `github/labels.txt`, `README.md`
- Crear: `AGENTS.md` (en la raíz de `ai-dev-team`)

- [ ] **Paso 1: Labels.** Agregar a `github/labels.txt`:

```
agent:qa|0e8a16|QA prueba el comportamiento de este PR (lo pone el dispatcher)
agent:docs|c2e0c6|El agente de docs documenta este issue
```

Ejecutar:

```bash
for r in ai-dev-team agent-playground qr-generator; do scripts/sync-labels.sh maxiar-org/$r >/dev/null; done
```

Resultado esperado: `gh label list --repo maxiar-org/ai-dev-team | grep -c "agent:"` muestra `6`.

- [ ] **Paso 2: Compose y `.env`.**
  - En `docker-compose.yml`, en el `environment` del dispatcher, debajo de `PROJECT_NUMBER`, agregar:

```yaml
      QA_ENGINE: ${QA_ENGINE:-codex}
      DOCS_ENGINE: ${DOCS_ENGINE:-claude}
      DOCS_ONLY_REPOS: ${DOCS_ONLY_REPOS:-}
```

  - En `.env.example` y en `.env`, agregar `QA_ENGINE=codex`, `DOCS_ENGINE=claude` y `DOCS_ONLY_REPOS=ai-dev-team`, y cambiar `REPOS` a `agent-playground,qr-generator,ai-dev-team`.
  - En `.env.example`, comentar cada variable nueva: QA usa el navegador; docs escribe mejor con Claude; y la lista de repos donde los agentes solo pueden tocar documentación.

- [ ] **Paso 3: `AGENTS.md` de `ai-dev-team`** (raíz del repo):

```markdown
# AGENTS.md: ai-dev-team

Este repo es el framework del AI Dev Team: el dispatcher (Python), las plantillas de roles, Docker y la documentación.

## ⚠️ Repo de solo documentación
Los agentes **solo** pueden modificar `docs/` (sitio Starlight), archivos `.md` y `.github/workflows/docs.yml`. El código del dispatcher, `roles/`, Docker y la configuración los cambian Eduardo y Claude Code. Cualquier cambio fuera de eso es bloqueante en la review.

## Documentación (Starlight)
- El sitio vive en `docs/` (contenido en `docs/src/content/docs/`) y se publica en https://maxiar-org.github.io/ai-dev-team/.
- `docs/superpowers/` (specs y planes) y `docs/bitacora.md` son documentos de trabajo: no se mueven ni se borran. Se pueden enlazar desde el sitio.
- Verificación antes del PR: `cd docs && npm ci && npm run build`.

## Probar la UI
```bash
cd docs && npm ci && npm run build && npx astro preview --port 8765 --host 0.0.0.0 >/dev/null 2>&1 &
```
Abre `http://localhost:8765/ai-dev-team/` y recorre el índice, la búsqueda y cada página nueva.

## Convenciones
- Español rioplatense, claro, con ejemplos. Diagramas Mermaid para los flujos.
- Ramas `agent/<issue>-<slug>`. Un PR por issue, con `Closes #<issue>` y la sección **Entregable visible**.
```

- [ ] **Paso 4: README.** En la tabla "Cómo funciona" de `README.md`:
  - Agregar las filas:
    - "| Pones `agent:docs` en un issue | El agente de docs (Claude por defecto) actualiza el sitio Starlight y abre un PR |"
    - "| — | Después de la aprobación del reviewer, QA (Codex) prueba la app con Playwright: `QA: OK` → te pide review; `QA: FALLA` → vuelve al dev |"
  - Cambiar la fila de `VEREDICTO: APROBADO` para que diga que pasa a QA.

- [ ] **Paso 5: Desplegar y verificar.**

```bash
cd dispatcher && uv run pytest -q && cd ..
docker compose up -d --build dispatcher
sleep 20 && docker compose logs dispatcher --since 1m | grep -vE "httpx" | tail -3
docker compose exec dispatcher python -c "from dispatcher.config import Config; c=Config.from_env(); print(c.repos, c.docs_only_repos, c.qa_engine, c.docs_engine)"
```

Resultado esperado: sin errores, y `('agent-playground', 'qr-generator', 'ai-dev-team') ('ai-dev-team',) codex claude`.

- [ ] **Paso 6: GitHub Pages con origen Actions en los dos repos.**

```bash
for r in qr-generator ai-dev-team; do gh api -X POST repos/maxiar-org/$r/pages -f build_type=workflow --jq .html_url 2>&1 | tail -1; done
```

Resultado esperado: dos URLs `https://maxiar-org.github.io/<repo>/`. Si responde `409` porque Pages ya existe, verificar con `gh api repos/maxiar-org/<repo>/pages --jq .build_type`, que debe dar `workflow`.

- [ ] **Paso 7: Copiar la plantilla de issue a `ai-dev-team`** (`.github/ISSUE_TEMPLATE/agent-task.md`, la misma de `github/ISSUE_TEMPLATE/`). Hacer commit y push de todo:

```bash
git add -A docker-compose.yml .env.example github README.md AGENTS.md .github && git commit -m "feat: desplegar roles QA y Docs; ai-dev-team como repo de solo documentación" && git push
```

---

### Tarea 6: Issues de estreno

- [ ] **Paso 1: Crear los dos issues** (sin label de agente; los etiqueta Eduardo):
  - **`qr-generator`:** "Docs: sitio Starlight con guía de uso y arquitectura". Contenido según la sección 7 del spec: inicio; guía para Maxi (cada tipo de QR, imprimir con WePrint, instalar en el iPhone); arquitectura de la app; decisiones (Reseñas, Mercado Pago, impresión directa) enlazando `docs/*.md`; deploy a Pages. Entregable visible: `https://maxiar-org.github.io/qr-generator/`.
  - **`ai-dev-team`:** "Docs: sitio Starlight del AI Dev Team y lecciones del piloto". Contenido: qué es y cómo funciona (diagrama Mermaid del flujo dev → review → QA → Eduardo), roles, labels, cómo sumar un proyecto, operación (arrancar, credenciales, métricas, tablero) y lecciones del piloto (resumen de `pilot/REPORT.md`). Los specs y planes quedan fuera del sidebar. Entregable visible: `https://maxiar-org.github.io/ai-dev-team/`.

- [ ] **Paso 2:** avisar a Eduardo que les ponga `agent:docs` a los dos. Esperar el ciclo docs → review → QA → pedido de review y verificar:
  - que QA dejó evidencia en `qa-evidence`;
  - que, después del merge, cada sitio carga en GitHub Pages: `curl -s -o /dev/null -w "%{http_code}" https://maxiar-org.github.io/<repo>/` da `200`.
