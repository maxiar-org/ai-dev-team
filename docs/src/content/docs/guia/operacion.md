---
title: Operación
description: Arrancar con Docker, credenciales, métricas y cómo sumar un proyecto.
sidebar:
  order: 5
---

## Arrancar

```bash
cp .env.example .env        # completar (ver Credenciales)
docker compose up -d --build
docker compose logs -f dispatcher
```

Esto levanta dos servicios: **canvas** (el runtime de agentes, con la UI en `http://localhost:8000/canvas`, pide la
`CANVAS_API_KEY`) y **dispatcher** (el orquestador, sin interfaz propia — se opera por su CLI y por los logs).

## Credenciales

Ninguna credencial se sube al repo: todas van en `.env` (está en `.gitignore`). El `.env.example` tiene la lista
completa de variables; estas son las que requieren un paso manual:

- **Claude (cuenta Pro del piloto):** se genera con `claude setup-token` dentro de un contenedor temporal, iniciando
  sesión en una ventana de incógnito **solo** con la cuenta Pro (nunca una cuenta Max de clientes). El token
  (`sk-ant-oat01-…`) dura un año y va en `CLAUDE_CODE_OAUTH_TOKEN`.
- **Codex (ChatGPT):** se habilita el login por código de dispositivo en la configuración de seguridad de ChatGPT y
  se genera `codex_auth.json` con `codex login --device-auth` dentro de un contenedor temporal. Su contenido (una
  línea) va en `CODEX_AUTH_JSON`, y después se borra el archivo local.
- **Respaldo pagado:** si las suscripciones no alcanzan, se puede agregar `ANTHROPIC_API_KEY` al servicio `canvas`
  del compose y vaciar `CLAUDE_CODE_OAUTH_TOKEN`, con un tope acordado en USD.

Los pasos exactos (comandos de `docker run`, dónde pegar cada token) están en el `README.md` del repo, sección
Credenciales.

## Métricas

Cada tarea terminada agrega una fila a `pilot/metrics.csv`: repo, issue o PR, rol, motor, duración, tokens y costo
estimado. Para ver el resumen:

```bash
docker compose run --rm dispatcher report
```

Imprime tres tablas en Markdown: tareas y costo por motor (con el máximo de tareas en cualquier ventana de 5
horas), cantidad de tareas por resultado (`pr_abierto`, `aprobado`, `qa_ok`, `needs_human`, …) y qué PRs están
mergeados.

## Agregar un proyecto nuevo

1. `scripts/sync-labels.sh maxiar-org/<repo>` — crea o actualiza los labels del equipo en ese repo.
2. Copiá `github/ISSUE_TEMPLATE/agent-task.md` a `.github/ISSUE_TEMPLATE/` del repo nuevo.
3. Agregá el repo a `REPOS` en `.env` (separado por coma).
4. `docker compose up -d` para que el dispatcher lo recargue.

Si el repo nuevo es de **solo documentación** (como `ai-dev-team`), agregalo también a `DOCS_ONLY_REPOS`: el
dispatcher no va a dejar arrancar `agent:dev` ahí, solo `agent:docs`.

## Si una tarea queda trabada

Si un issue o PR queda con `agent:working` pero no avanza, revisá la conversación en Canvas. Si hace falta
liberarla a mano: quitá el label en GitHub y borrá la tarea de `state.json`
(`docker compose exec dispatcher sh`, el archivo está en `/state/state.json`).

## Siguiente paso

Para ver qué aprendimos del piloto que dio origen a este equipo, seguí con [Lecciones del piloto](/ai-dev-team/piloto/lecciones/).
