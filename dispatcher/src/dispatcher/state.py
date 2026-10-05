"""Estado efímero del dispatcher. Lo importante vive en los labels de GitHub."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .models import ActiveTask


@dataclass
class State:
    active: dict[str, ActiveTask] = field(default_factory=dict)
    processed_comments: set[int] = field(default_factory=set)
    review_rounds: dict[str, int] = field(default_factory=dict)
    comments_since: str | None = None
    conflict_attempts: dict[str, int] = field(default_factory=dict)
    blocked_notified: dict[str, list[int]] = field(default_factory=dict)
    qa_rounds: dict[str, int] = field(default_factory=dict)
    docs_only_notified: set[str] = field(default_factory=set)


class StateStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> State:
        if not self.path.exists():
            return State()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return State(
            active={k: ActiveTask(**v) for k, v in data.get("active", {}).items()},
            processed_comments=set(data.get("processed_comments", [])),
            review_rounds=dict(data.get("review_rounds", {})),
            comments_since=data.get("comments_since"),
            conflict_attempts=dict(data.get("conflict_attempts", {})),
            blocked_notified={k: list(v) for k, v in data.get("blocked_notified", {}).items()},
            qa_rounds=dict(data.get("qa_rounds", {})),
            docs_only_notified=set(data.get("docs_only_notified", [])),
        )

    def save(self, state: State) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "active": {k: asdict(v) for k, v in state.active.items()},
            "processed_comments": sorted(state.processed_comments),
            "review_rounds": state.review_rounds,
            "comments_since": state.comments_since,
            "conflict_attempts": state.conflict_attempts,
            "blocked_notified": state.blocked_notified,
            "qa_rounds": state.qa_rounds,
            "docs_only_notified": sorted(state.docs_only_notified),
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)
