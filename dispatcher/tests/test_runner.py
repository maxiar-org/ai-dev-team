import pytest

from dispatcher.metrics import MetricsLog
from dispatcher.models import Comment, Item
from dispatcher.runner import Dispatcher
from dispatcher.state import StateStore

from .fakes import Clock, FakeCanvas, FakeGitHub, FakeWorkspace

REPO = "qr-generator"


def make(tmp_path, cfg, calls=None):
    gh, cv = FakeGitHub(calls), FakeCanvas(calls)
    ws, clock = FakeWorkspace(tmp_path / "projects"), Clock(10_000.0)
    d = Dispatcher(cfg, gh, cv, ws, StateStore(cfg.state_path), MetricsLog(cfg.metrics_path), clock=clock)
    return d, gh, cv, ws, clock


def test_issue_goes_from_label_to_pr_review(tmp_path, cfg):
    d, gh, cv, ws, clock = make(tmp_path, cfg)
    gh.add_item(Item(REPO, 3, "issue", "QR de WhatsApp", "Normalizar números", frozenset({"agent:dev"})))

    d.run_once()
    [(engine, workdir, prompt)] = cv.created
    assert engine == "codex" and workdir.endswith("qr-generator/issue-3")
    assert "QR de WhatsApp" in prompt and "agent/3-qr-de-whatsapp" in prompt
    assert gh.labels(3) == {"agent:working"}

    gh.add_item(Item(REPO, 7, "pr", "WA", "Closes #3", frozenset(), "agent/3-qr-de-whatsapp"))
    cv.status["conv1"] = "finished"
    clock.now += 600
    d.run_once()

    assert gh.labels(3) == set()
    assert gh.labels(7) == {"agent:review", "engine:codex"}
    [row] = MetricsLog(cfg.metrics_path).read()
    assert (row["resultado"], row["duracion_min"], row["tokens_entrada"]) == ("pr_abierto", "10.0", "100")
    assert StateStore(cfg.state_path).load().active == {}
    assert len(cv.created) == 1  # la review arranca en el ciclo siguiente


def test_review_with_changes_requests_fix(tmp_path, cfg):
    d, gh, cv, ws, clock = make(tmp_path, cfg)
    gh.add_item(Item(REPO, 7, "pr", "WA", "Closes #3", frozenset({"agent:review", "engine:codex"}), "agent/3-wa"))

    d.run_once()
    [(engine, workdir, prompt)] = cv.created
    assert engine == "claude" and workdir.endswith("qr-generator/pr-7") and "VEREDICTO" in prompt
    assert ws.prepared == [(REPO, "pr", 7, "agent/3-wa")]

    cv.status["conv1"] = "finished"
    cv.responses["conv1"] = "Falta un test.\nVEREDICTO: CAMBIOS"
    d.run_once()
    assert gh.labels(7) == {"engine:codex", "agent:fix"}
    assert StateStore(cfg.state_path).load().review_rounds == {f"{REPO}#7": 1}


def test_canvas_busy_leaves_github_untouched(tmp_path, cfg):
    d, gh, cv, ws, clock = make(tmp_path, cfg)
    cv.busy = True
    gh.add_item(Item(REPO, 3, "issue", "T", "", frozenset({"agent:dev"})))
    d.run_once()
    assert gh.labels(3) == {"agent:dev"}
    assert StateStore(cfg.state_path).load().active == {}


def test_workspace_failure_escalates_to_human(tmp_path, cfg):
    d, gh, cv, ws, clock = make(tmp_path, cfg)
    ws.fail = True
    gh.add_item(Item(REPO, 3, "issue", "T", "", frozenset({"agent:dev"})))
    d.run_once()
    assert "needs:human" in gh.labels(3)
    assert "git clone falló" in gh.posted[0][1]
    assert cv.created == []


def test_eduardo_comment_resumes_issue_once(tmp_path, cfg):
    d, gh, cv, ws, clock = make(tmp_path, cfg)
    gh.add_item(Item(REPO, 3, "issue", "WA", "", frozenset({"needs:human"})))
    gh.comments.append(Comment(55, REPO, 3, "maxiar", "@openhands es para Argentina"))

    d.run_once()
    [(_, _, prompt)] = cv.created
    assert "es para Argentina" in prompt
    assert gh.labels(3) == {"agent:working"}

    cv.status["conv1"] = "finished"
    d.run_once()  # termina sin PR → needs:human
    d.run_once()  # el comentario 55 ya está procesado
    assert len(cv.created) == 1
    assert "needs:human" in gh.labels(3)


def test_canvas_is_read_before_github(tmp_path, cfg):
    calls: list[str] = []
    d, *_ = make(tmp_path, cfg, calls)
    d.run_once()
    assert calls.index("canvas.get_conversations") < calls.index("github.list_open_items")


def test_failing_action_does_not_stop_the_cycle(tmp_path, cfg):
    d, gh, cv, ws, clock = make(tmp_path, cfg)
    gh.add_item(Item(REPO, 1, "issue", "T", "", frozenset({"agent:dev"})))
    gh.add_item(Item(REPO, 7, "pr", "PR", "", frozenset({"agent:review", "engine:codex"}), "agent/9-x"))
    gh.fail_add_labels_for = {1}
    d.run_once()
    assert [engine for engine, _, _ in cv.created] == ["claude"]
    assert gh.labels(7) == {"engine:codex", "agent:working"}


def test_timeout_pauses_and_escalates(tmp_path, cfg):
    d, gh, cv, ws, clock = make(tmp_path, cfg)
    gh.add_item(Item(REPO, 3, "issue", "T", "", frozenset({"agent:dev"})))
    d.run_once()
    clock.now += cfg.task_timeout_min * 60
    d.run_once()
    assert cv.paused == ["conv1"]
    assert "needs:human" in gh.labels(3)
    assert "timeout" in gh.posted[-1][1]


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

def test_final_response_is_redacted_before_posting(tmp_path, cfg):
    d, gh, cv, ws, clock = make(tmp_path, cfg)
    gh.add_item(Item(REPO, 3, "issue", "T", "", frozenset({"agent:dev"})))
    d.run_once()
    cv.status["conv1"] = "finished"
    cv.responses["conv1"] = "remote: https://x-access-token:ghp_test@github.com/x.git\nGH_TOKEN=ghp_test"
    d.run_once()
    body = gh.posted[-1][1]
    assert "ghp_test" not in body and "x-access-token:" not in body


def test_orphan_working_label_is_released(tmp_path, cfg):
    d, gh, cv, ws, clock = make(tmp_path, cfg)
    gh.add_item(Item(REPO, 3, "issue", "T", "", frozenset({"agent:working"})))
    d.run_once()
    assert gh.labels(3) == {"needs:human"}
    assert "agent:working" in gh.posted[0][1]
    assert cv.created == []


def test_board_follows_labels(tmp_path, cfg):
    from .fakes import FakeBoard

    gh, cv = FakeGitHub(), FakeCanvas()
    board = FakeBoard()
    d = Dispatcher(cfg, gh, cv, FakeWorkspace(tmp_path / "p"), StateStore(cfg.state_path),
                   MetricsLog(cfg.metrics_path), clock=Clock(10_000.0), board=board)
    gh.add_item(Item(REPO, 3, "issue", "T", "", frozenset({"agent:dev"}), node_id="I_3"))
    gh.add_item(Item(REPO, 4, "issue", "U", "", frozenset(), node_id="I_4"))
    board.node_to_key = {"I_3": f"{REPO}#3", "I_4": f"{REPO}#4"}
    d.run_once()  # agrega al tablero con la columna vista al inicio del ciclo
    assert board.items[f"{REPO}#3"][1] == "Listo para agentes"
    assert board.items[f"{REPO}#4"][1] == "Backlog"
    d.run_once()  # el ciclo siguiente ve agent:working
    assert board.items[f"{REPO}#3"][1] == "En curso"


def test_board_failure_does_not_break_the_cycle(tmp_path, cfg):
    from .fakes import FakeBoard

    gh, cv = FakeGitHub(), FakeCanvas()
    board = FakeBoard()
    board.fail = True
    d = Dispatcher(cfg, gh, cv, FakeWorkspace(tmp_path / "p"), StateStore(cfg.state_path),
                   MetricsLog(cfg.metrics_path), clock=Clock(10_000.0), board=board)
    gh.add_item(Item(REPO, 3, "issue", "T", "", frozenset({"agent:dev"})))
    d.run_once()
    assert len(cv.created) == 1


def test_review_comment_from_eduardo_triggers_fix(tmp_path, cfg):
    d, gh, cv, ws, clock = make(tmp_path, cfg)
    gh.add_item(Item(REPO, 11, "pr", "IG", "", frozenset({"engine:codex"}), "agent/3-instagram"))
    gh.comments.append(Comment(-6, REPO, 11, "maxiar", "@openhands resolvé los conflictos con main"))
    d.run_once()
    [(engine, workdir, prompt)] = cv.created
    assert engine == "codex" and workdir.endswith("pr-11") and "resolvé los conflictos" in prompt



def test_conflicting_pr_is_fixed_then_reviewed_again(tmp_path, cfg):
    d, gh, cv, ws, clock = make(tmp_path, cfg)
    gh.add_item(Item(REPO, 12, "pr", "Diseño", "", frozenset({"engine:claude"}), "agent/4-diseno"))
    gh.merge_states[12] = "dirty"
    d.run_once()
    [(engine, workdir, prompt)] = cv.created
    assert engine == "claude" and workdir.endswith("pr-12") and "conflictos" in prompt
    assert StateStore(cfg.state_path).load().conflict_attempts == {f"{REPO}#12": 1}
    cv.status["conv1"] = "finished"
    gh.merge_states[12] = "clean"
    d.run_once()
    assert "agent:review" in gh.labels(12)
    assert StateStore(cfg.state_path).load().conflict_attempts == {}


def test_conflict_that_keeps_failing_escalates(tmp_path, cfg):
    d, gh, cv, ws, clock = make(tmp_path, cfg)
    gh.add_item(Item(REPO, 12, "pr", "Diseño", "", frozenset({"engine:codex"}), "agent/4-diseno"))
    gh.merge_states[12] = "dirty"
    for _ in range(20):  # fix → review aprobada → QA OK → sigue con conflictos → otro fix → ... → escala
        d.run_once()
        for conv_id in cv.status:
            cv.status[conv_id] = "finished"
            cv.responses[conv_id] = "VEREDICTO: APROBADO\nQA: OK"
        if "needs:human" in gh.labels(12):
            break
    fixes = [m for _, _, m in cv.created if "conflictos con la rama base" in m]
    assert len(fixes) == 2
    assert "needs:human" in gh.labels(12)
    assert "conflictos" in gh.posted[-1][1]

def test_blocked_issue_gets_a_single_notice(tmp_path, cfg):
    d, gh, cv, ws, clock = make(tmp_path, cfg)
    gh.add_item(Item(REPO, 5, "issue", "Guardar", "Depende de #4", frozenset({"agent:dev"})))
    gh.add_item(Item(REPO, 4, "issue", "Diseño", "", frozenset()))
    d.run_once()
    d.run_once()
    assert cv.created == []
    assert len(gh.posted) == 1 and "#4" in gh.posted[0][1]


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


def test_heartbeat_written_only_after_successful_cycle(tmp_path, cfg):
    import dataclasses

    hb = tmp_path / "hb"
    cfg2 = dataclasses.replace(cfg, heartbeat_path=hb)
    d, gh, cv, ws, clock = make(tmp_path, cfg2)
    d.run_once()
    assert hb.read_text() == "10000.0"
    clock.now += 60
    gh.list_open_items = lambda repo: (_ for _ in ()).throw(RuntimeError("GitHub caído"))
    with pytest.raises(RuntimeError):
        d.run_once()
    assert hb.read_text() == "10000.0"
    assert not list(tmp_path.glob("hb.*"))  # escritura atómica: no quedan temporales


def test_metrics_failure_does_not_block_finishing(tmp_path, cfg):
    import dataclasses

    bad = tmp_path / "soy-un-directorio"
    bad.mkdir()
    d, gh, cv, ws, clock = make(tmp_path, dataclasses.replace(cfg, metrics_path=bad))
    gh.add_item(Item(REPO, 7, "pr", "WA", "", frozenset({"agent:review", "engine:codex"}), "agent/3-wa"))
    d.run_once()
    cv.status["conv1"] = "finished"
    cv.responses["conv1"] = "VEREDICTO: APROBADO"
    d.run_once()
    assert StateStore(cfg.state_path).load().active == {}
    assert gh.labels(7) == {"engine:codex", "agent:qa"}
    d.run_once()  # no repite el cierre
    assert len(cv.created) == 2  # el ciclo siguiente arrancó QA, no se trabó
