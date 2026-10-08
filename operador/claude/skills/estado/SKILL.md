---
name: estado
description: Resumen del estado del AI Dev Team y de cada proyecto (hecho, en curso, bloqueado, qué espera a Eduardo) con acciones sugeridas. Usar cuando Eduardo pregunta "status", "estado", "cómo vamos" o similar.
---

# Estado del AI Dev Team

1. Lee `REPOS` y `DOCS_ONLY_REPOS` de `/opt/ai-dev-team/.env`.
2. Para cada repo de `maxiar-org` en `REPOS`, usa `gh`:
   - `gh issue list --repo maxiar-org/<repo> --state open --json number,title,labels`
   - `gh pr list --repo maxiar-org/<repo> --state open --json number,title,labels,mergeStateStatus,reviewDecision,reviewRequests`
   - `gh pr list --repo maxiar-org/<repo> --state merged --limit 10 --json number,title,mergedAt`, para lo mergeado en las últimas 48 h.
3. Tablero: `gh project item-list 1 --owner maxiar-org --format json`, para las columnas que no están en Hecho.
4. Stack: `docker compose ps`, issues `[ops]` abiertos (`gh issue list --repo maxiar-org/ai-dev-team --label ops`) y tareas activas (`docker compose exec dispatcher cat /state/state.json`).
5. Actividad: `docker compose logs dispatcher --since 24h | grep -E "Inició|Terminó|Falló"`.
6. Consumo, si te lo piden: `docker compose run --rm dispatcher report`.

Responde con este formato:
- Una línea de **resumen general**.
- Una **tabla** por proyecto: issue y PR, estado (✅ hecho, 🔄 en curso, ⏳ espera a Eduardo, ⏸️ bloqueado, ⚠️ problema) y un detalle corto.
- **Qué espera a Eduardo**: reviews, `needs:human` y decisiones.
- **Acciones sugeridas** numeradas y en orden, incluido el orden de merge si hay PRs que tocan los mismos archivos.
- Alertas `[ops]` abiertas, si las hay.
