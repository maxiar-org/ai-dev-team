"""Cliente mínimo de GitHub Projects (v2) por GraphQL para el tablero del equipo."""

from __future__ import annotations

from typing import Any

import httpx

LOAD_QUERY = """
query($org: String!, $n: Int!, $after: String) {
  organization(login: $org) {
    projectV2(number: $n) {
      id
      field(name: "Status") { ... on ProjectV2SingleSelectField { id options { id name } } }
      items(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          fieldValueByName(name: "Status") { ... on ProjectV2ItemFieldSingleSelectValue { name } }
          content {
            ... on Issue { number repository { name } }
            ... on PullRequest { number repository { name } }
          }
        }
      }
    }
  }
}
"""

ADD_MUTATION = """
mutation($p: ID!, $c: ID!) {
  addProjectV2ItemById(input: {projectId: $p, contentId: $c}) { item { id } }
}
"""

SET_MUTATION = """
mutation($p: ID!, $i: ID!, $f: ID!, $o: String!) {
  updateProjectV2ItemFieldValue(
    input: {projectId: $p, itemId: $i, fieldId: $f, value: {singleSelectOptionId: $o}}
  ) { projectV2Item { id } }
}
"""


class ProjectError(RuntimeError):
    """Falló una operación sobre el tablero."""


class ProjectBoard:
    def __init__(self, token: str, org: str, number: int, http: httpx.Client | None = None,
                 base_url: str = "https://api.github.com"):
        self.org = org
        self.number = number
        self.http = http or httpx.Client(
            base_url=base_url, timeout=30, headers={"Authorization": f"Bearer {token}"}
        )
        self.project_id: str | None = None
        self.field_id: str | None = None
        self.options: dict[str, str] = {}

    def _gql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        resp = self.http.post("/graphql", json={"query": query, "variables": variables})
        resp.raise_for_status()
        body = resp.json()
        if body.get("errors"):
            raise ProjectError("; ".join(e.get("message", "") for e in body["errors"]))
        return body["data"]

    def load(self) -> dict[str, tuple[str, str | None]]:
        """Devuelve {"repo#numero": (id_del_item, columna_actual)} y cachea ids del proyecto."""
        current: dict[str, tuple[str, str | None]] = {}
        after: str | None = None
        while True:
            data = self._gql(LOAD_QUERY, {"org": self.org, "n": self.number, "after": after})
            project = (data.get("organization") or {}).get("projectV2")
            if project is None:
                raise ProjectError(f"No encontré el proyecto #{self.number} de {self.org}")
            field = project.get("field") or {}
            self.project_id = project["id"]
            self.field_id = field.get("id")
            self.options = {o["name"]: o["id"] for o in field.get("options", [])}
            for node in project["items"]["nodes"]:
                content = node.get("content")
                if not content or "number" not in content:
                    continue  # borradores u objetos sin acceso
                key = f"{content['repository']['name']}#{content['number']}"
                status = (node.get("fieldValueByName") or {}).get("name")
                current[key] = (node["id"], status)
            info = project["items"]["pageInfo"]
            if not info["hasNextPage"]:
                return current
            after = info["endCursor"]

    def add(self, content_node_id: str) -> str:
        data = self._gql(ADD_MUTATION, {"p": self.project_id, "c": content_node_id})
        return data["addProjectV2ItemById"]["item"]["id"]

    def set_column(self, item_id: str, column: str) -> None:
        option = self.options.get(column)
        if option is None:
            raise ProjectError(f"El tablero no tiene la columna {column!r}")
        self._gql(SET_MUTATION, {"p": self.project_id, "i": item_id, "f": self.field_id, "o": option})
