"""Cliente mínimo de la API REST de GitHub."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from .models import Comment, Item


class GitHubClient:
    def __init__(
        self,
        token: str,
        org: str,
        http: httpx.Client | None = None,
        base_url: str = "https://api.github.com",
    ):
        self.org = org
        self.http = http or httpx.Client(
            base_url=base_url,
            timeout=30,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def _repo(self, repo: str) -> str:
        return f"/repos/{self.org}/{repo}"

    def _paginate(self, path: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        url: str | None = path
        query: dict[str, Any] | None = params
        while url:
            resp = self.http.get(url, params=query)
            resp.raise_for_status()
            results.extend(resp.json())
            url = resp.links.get("next", {}).get("url")
            query = None  # la URL "next" ya trae los parámetros
        return results

    def list_open_items(self, repo: str) -> list[Item]:
        base = self._repo(repo)
        heads = {
            p["number"]: p["head"]["ref"]
            for p in self._paginate(f"{base}/pulls", {"state": "open", "per_page": 100})
        }
        items = []
        for raw in self._paginate(f"{base}/issues", {"state": "open", "per_page": 100}):
            is_pr = "pull_request" in raw
            items.append(
                Item(
                    repo=repo,
                    number=raw["number"],
                    kind="pr" if is_pr else "issue",
                    title=raw["title"],
                    body=raw.get("body") or "",
                    labels=frozenset(label["name"] for label in raw.get("labels", [])),
                    head_ref=heads.get(raw["number"]) if is_pr else None,
                    node_id=raw.get("node_id", ""),
                )
            )
        return items

    def list_comments_since(self, repo: str, since: str) -> list[Comment]:
        raw = self._paginate(
            f"{self._repo(repo)}/issues/comments",
            {"since": since, "per_page": 100, "sort": "created", "direction": "asc"},
        )
        return [
            Comment(
                id=c["id"],
                repo=repo,
                number=int(c["issue_url"].rsplit("/", 1)[1]),
                author=(c.get("user") or {}).get("login", ""),
                body=c.get("body") or "",
            )
            for c in raw
        ]

    def list_pr_reviews_since(self, repo: str, numbers: Iterable[int], since: str) -> list[Comment]:
        """Reviews de PR con texto, como comentarios. Su id es negativo para no chocar con los
        ids de comentarios de issues en processed_comments."""
        threshold = datetime.fromisoformat(since.replace("Z", "+00:00"))
        out: list[Comment] = []
        for number in numbers:
            for r in self._paginate(f"{self._repo(repo)}/pulls/{number}/reviews", {"per_page": 100}):
                submitted = r.get("submitted_at")
                body = r.get("body") or ""
                if not submitted or not body.strip():
                    continue
                if datetime.fromisoformat(submitted.replace("Z", "+00:00")) < threshold:
                    continue
                author = (r.get("user") or {}).get("login", "")
                out.append(Comment(id=-r["id"], repo=repo, number=number, author=author, body=body))
        return out

    def get_labels(self, repo: str, number: int) -> frozenset[str]:
        resp = self.http.get(f"{self._repo(repo)}/issues/{number}")
        resp.raise_for_status()
        return frozenset(label["name"] for label in resp.json().get("labels", []))

    def add_labels(self, repo: str, number: int, labels: Iterable[str]) -> None:
        resp = self.http.post(f"{self._repo(repo)}/issues/{number}/labels", json={"labels": list(labels)})
        resp.raise_for_status()

    def remove_label(self, repo: str, number: int, label: str) -> None:
        resp = self.http.delete(f"{self._repo(repo)}/issues/{number}/labels/{quote(label, safe=':')}")
        if resp.status_code != 404:
            resp.raise_for_status()

    def comment(self, repo: str, number: int, body: str) -> None:
        resp = self.http.post(f"{self._repo(repo)}/issues/{number}/comments", json={"body": body})
        resp.raise_for_status()

    def request_review(self, repo: str, number: int, reviewers: Iterable[str]) -> None:
        resp = self.http.post(
            f"{self._repo(repo)}/pulls/{number}/requested_reviewers",
            json={"reviewers": list(reviewers)},
        )
        resp.raise_for_status()

    def list_open_issue_titles(self, repo: str, label: str) -> dict[str, int]:
        raw = self._paginate(f"{self._repo(repo)}/issues", {"state": "open", "labels": label, "per_page": 100})
        return {i["title"]: i["number"] for i in raw if "pull_request" not in i}

    def create_issue(self, repo: str, title: str, body: str, labels: Iterable[str]) -> None:
        resp = self.http.post(f"{self._repo(repo)}/issues", json={"title": title, "body": body, "labels": list(labels)})
        resp.raise_for_status()

    def close_issue(self, repo: str, number: int, comment: str) -> None:
        self.comment(repo, number, comment)
        resp = self.http.patch(f"{self._repo(repo)}/issues/{number}", json={"state": "closed"})
        resp.raise_for_status()

    def get_merge_state(self, repo: str, number: int) -> str | None:
        """mergeable_state del PR ("dirty" = conflictos; None mientras GitHub lo calcula)."""
        resp = self.http.get(f"{self._repo(repo)}/pulls/{number}")
        resp.raise_for_status()
        return resp.json().get("mergeable_state")

    def is_merged(self, repo: str, number: int) -> bool:
        resp = self.http.get(f"{self._repo(repo)}/pulls/{number}")
        resp.raise_for_status()
        return bool(resp.json().get("merged"))

    def pr_details(self, repo: str, number: int) -> dict:
        resp = self.http.get(f"{self._repo(repo)}/pulls/{number}")
        resp.raise_for_status()
        pr = resp.json()
        sha = pr["head"]["sha"]
        files = tuple(f["filename"] for f in self._paginate(f"{self._repo(repo)}/pulls/{number}/files", {"per_page": 100}))
        runs = self.http.get(f"{self._repo(repo)}/actions/runs", params={"head_sha": sha, "per_page": 20})
        runs.raise_for_status()
        wr = runs.json().get("workflow_runs", [])
        if not wr:
            ci = "none"
        elif any(r.get("conclusion") in ("failure", "cancelled", "timed_out") for r in wr):
            ci = "failure"
        elif any(r.get("status") != "completed" for r in wr):
            ci = "pending"
        else:
            ci = "success"
        return {"head_sha": sha, "head_ref": pr["head"]["ref"], "mergeable_state": pr.get("mergeable_state"),
                "files": files, "ci": ci}

    def last_comment_by(self, repo: str, number: int, login: str) -> str | None:
        comments = self._paginate(f"{self._repo(repo)}/issues/{number}/comments", {"per_page": 100})
        mine = [c.get("body") or "" for c in comments if (c.get("user") or {}).get("login") == login]
        return mine[-1] if mine else None
