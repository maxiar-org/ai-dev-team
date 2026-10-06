---
title: Labels y tablero
description: Tabla de labels y columnas del Kanban.
sidebar:
  order: 4
---

## Labels

Los labels viven en `github/labels.txt` y se instalan en cada repo con `scripts/sync-labels.sh`. El dispatcher los
lee y los pone; vos normalmente solo ponés el primero de cada issue (`agent:dev` o `agent:docs`).

| Label | Quién lo pone | Qué significa |
|---|---|---|
| `agent:dev` | Vos | El dev debe implementar este issue |
| `agent:docs` | Vos | El agente de docs debe documentar este issue |
| `agent:working` | El dispatcher | Hay una conversación de Canvas corriendo para este issue o PR |
| `agent:review` | El dispatcher | El reviewer debe revisar este PR |
| `agent:qa` | El dispatcher | El QA debe probar el comportamiento de este PR |
| `agent:fix` | El dispatcher | El dev debe atender la review o el QA de este PR |
| `needs:human` | El dispatcher o un agente | Hace falta una decisión tuya; respondé con `@openhands ...` |
| `engine:claude` | Vos (opcional) | Fuerza el motor Claude Code para este issue o PR |
| `engine:codex` | Vos (opcional) | Fuerza el motor Codex para este issue o PR |

`agent:working` siempre se quita al terminar la tarea, junto con el label que la disparó, para que no vuelva a
arrancar en bucle.

## El tablero

El dispatcher sincroniza cada issue y PR de los repos en `REPOS` contra el tablero de GitHub Projects de la
organización (`PROJECT_NUMBER` en `.env`), y lo mueve de columna según sus labels:

| Columna | Cuándo |
|---|---|
| **Backlog** | Issue sin ningún label de agente todavía |
| **Listo para agentes** | Issue con `agent:dev` o `agent:docs`, esperando que arranque (por ejemplo, por una dependencia pendiente) |
| **En curso** | Tiene `agent:working`: hay una conversación corriendo |
| **En review** | Es un PR que no está `En curso` ni `Necesita a Eduardo` (por ejemplo, esperando `agent:review` o `agent:qa`, o tu aprobación) |
| **Necesita a Eduardo** | Tiene `needs:human` |
| **Hecho** | El issue o PR ya no está abierto (cerrado o mergeado). La automatización nativa del tablero también la pone al cerrar o mergear; el dispatcher la asegura igual |

Un issue con PR abierto avanza junto con su PR: aunque el issue en sí sigue en `Backlog` o `Listo para agentes` por
sus propios labels, el tablero le muestra la columna del PR (por ejemplo, `En review`), porque es ahí donde está el
trabajo real.

## Siguiente paso

Para arrancar el equipo, ver las métricas o sumar un proyecto nuevo, seguí con [Operación](/ai-dev-team/guia/operacion/).
