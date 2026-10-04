"""Dobles de prueba con la misma interfaz que GitHubClient, CanvasClient y Workspace."""

from dataclasses import replace
from pathlib import Path

from dispatcher.canvas import CanvasBusy
from dispatcher.models import Comment, ConvInfo, Item
from dispatcher.workspace import WorkspaceError


class Clock:
    def __init__(self, now: float):
        self.now = now

    def __call__(self) -> float:
        return self.now


class FakeGitHub:
    def __init__(self, calls: list[str] | None = None):
        self.items: dict[tuple[str, int], Item] = {}
        self.comments: list[Comment] = []
        self.posted: list[tuple[int, str]] = []
        self.review_requests: list[tuple[int, tuple[str, ...]]] = []
        self.fail_add_labels_for: set[int] = set()
        self.fail_request_review = False
        self.calls = calls if calls is not None else []

    def add_item(self, item: Item) -> None:
        self.items[(item.repo, item.number)] = item

    def labels(self, number: int) -> set[str]:
        [item] = [i for (_, n), i in self.items.items() if n == number]
        return set(item.labels)

    def list_open_items(self, repo):
        self.calls.append("github.list_open_items")
        return [i for (r, _), i in sorted(self.items.items()) if r == repo]

    def list_comments_since(self, repo, since):
        return [c for c in self.comments if c.repo == repo and c.id > 0]

    def list_pr_reviews_since(self, repo, numbers, since):
        return [c for c in self.comments if c.repo == repo and c.id < 0 and c.number in numbers]

    def get_labels(self, repo, number):
        return self.items[(repo, number)].labels

    def add_labels(self, repo, number, labels):
        if number in self.fail_add_labels_for:
            raise RuntimeError("GitHub caído")
        item = self.items[(repo, number)]
        self.items[(repo, number)] = replace(item, labels=item.labels | set(labels))

    def remove_label(self, repo, number, label):
        item = self.items[(repo, number)]
        self.items[(repo, number)] = replace(item, labels=item.labels - {label})

    def comment(self, repo, number, body):
        self.posted.append((number, body))

    def request_review(self, repo, number, reviewers):
        if self.fail_request_review:
            raise RuntimeError("422: el usuario no es colaborador")
        self.review_requests.append((number, tuple(reviewers)))


class FakeCanvas:
    def __init__(self, calls: list[str] | None = None):
        self.created: list[tuple[str, str, str]] = []
        self.status: dict[str, str] = {}
        self.responses: dict[str, str] = {}
        self.paused: list[str] = []
        self.busy = False
        self.calls = calls if calls is not None else []

    def create_conversation(self, engine, working_dir, message):
        if self.busy:
            raise CanvasBusy("lleno")
        conv_id = f"conv{len(self.created) + 1}"
        self.created.append((engine, working_dir, message))
        self.status[conv_id] = "running"
        return conv_id

    def get_conversations(self, ids):
        self.calls.append("canvas.get_conversations")
        return {
            i: ConvInfo(i, self.status[i], prompt_tokens=100, completion_tokens=50)
            for i in ids
            if i in self.status
        }

    def final_response(self, conversation_id):
        return self.responses.get(conversation_id, "")

    def pause(self, conversation_id):
        self.paused.append(conversation_id)


class FakeWorkspace:
    def __init__(self, root: Path):
        self.root = root
        self.fail = False
        self.prepared: list[tuple[str, str, int, str | None]] = []

    def prepare(self, repo, kind, number, branch):
        if self.fail:
            raise WorkspaceError("git clone falló: repositorio no encontrado")
        self.prepared.append((repo, kind, number, branch))
        path = self.root / repo / f"{kind}-{number}"
        path.mkdir(parents=True, exist_ok=True)
        return path


class FakeBoard:
    def __init__(self):
        self.items: dict[str, tuple[str, str | None]] = {}
        self.node_to_key: dict[str, str] = {}
        self.fail = False

    def load(self):
        if self.fail:
            raise RuntimeError("Projects caído")
        return dict(self.items)

    def add(self, node_id):
        item_id = f"PVTI_{len(self.items) + 1}"
        self.items[self.node_to_key[node_id]] = (item_id, None)
        return item_id

    def set_column(self, item_id, column):
        for key, (iid, _) in self.items.items():
            if iid == item_id:
                self.items[key] = (iid, column)
