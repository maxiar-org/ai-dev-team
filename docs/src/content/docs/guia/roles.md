---
title: Roles
description: Qué hace cada agente, con qué motor y qué no hace.
sidebar:
  order: 3
---

Cada rol tiene una plantilla en `roles/*.md` (fuera del sitio) que arma el prompt exacto que recibe el agente.
Todos comparten dos reglas: nunca hacen push a `main` ni mergean PRs, y si les falta información comentan sus
preguntas, agregan `needs:human` y terminan — nunca inventan una decisión que te corresponde a vos.

## Dev

- **Qué hace:** implementa un issue con TDD (test que falla → código mínimo → refactor), en una rama
  `agent/<issue>-<slug>`, y abre el PR con `Closes #<issue>`, un resumen, cómo lo probó y una sección
  **Entregable visible**.
- **Motor:** Codex por defecto; el label `engine:claude` lo cambia a Claude Code.
- **Qué no hace:** no revisa su propio PR, no modifica el CI ni la protección de ramas salvo que el issue lo pida
  explícitamente, no mergea.

## Reviewer

- **Qué hace:** lee el issue, el diff completo y el CI del PR; busca bugs, casos borde, regresiones (que nada de lo
  que ya funcionaba en `main` se haya roto o desconectado) y que la sección Entregable visible funcione de verdad.
  Si el repo es de solo documentación, cualquier cambio fuera de `docs/`, `*.md` o el workflow de deploy es
  bloqueante. Publica un único comentario con `VEREDICTO: APROBADO` o `VEREDICTO: CAMBIOS`.
- **Motor:** siempre el **otro** motor del dev de ese PR — la revisión cruzada entre modelos es a propósito.
- **Qué no hace:** no toca código, no hace commits, no abre el navegador (eso es trabajo del QA) y no aprueba ni
  mergea en GitHub.

## QA

- **Qué hace:** una vez que el reviewer aprobó el código, prueba el **comportamiento**: escribe un plan de prueba
  numerado (un paso por criterio de aceptación más los flujos de regresión de `AGENTS.md`), compila y sirve la app,
  y lo ejecuta con Playwright, con una captura por paso relevante. Sube la evidencia a la rama huérfana
  `qa-evidence` y publica el resultado paso a paso con `QA: OK`, `QA: FALLA` (con pasos para reproducir, esperado y
  obtenido) o `QA: N/A` si el PR no tiene cambios visibles para la persona usuaria.
- **Motor:** Codex por defecto (`QA_ENGINE`).
- **Qué no hace:** no revisa ni modifica código, no hace commits en la rama del PR, no aprueba ni mergea.

## Docs

- **Qué hace:** escribe y mantiene el sitio Starlight del repo (este sitio, si estás leyendo sobre `ai-dev-team`),
  en español, con ejemplos y diagramas Mermaid cuando ayudan. Abre el PR con `Closes #<issue>` y una sección
  Entregable visible con la URL del sitio.
- **Motor:** Claude Code por defecto (`DOCS_ENGINE`).
- **Qué no hace:** nunca toca código de la aplicación ni del dispatcher — solo `docs/`, archivos `*.md` y el
  workflow de deploy de docs. En los repos **de solo documentación** (como este), el dispatcher ni siquiera deja
  arrancar una tarea de `agent:dev`: avisa con un comentario que hay que usar `agent:docs`.

## Fix

- **Qué hace:** retoma un PR existente para atender comentarios: el `VEREDICTO: CAMBIOS` del reviewer, el
  `QA: FALLA` del QA, un conflicto con `main`, o tu comentario `@openhands`. Corrige con TDD solo lo bloqueante,
  nunca descarta funcionalidad de `main`, y comenta en el PR qué corrigió, punto por punto.
- **Motor:** el mismo motor que venía usando el dev de ese PR.
- **Qué no hace:** no abre un PR nuevo (corrige el existente), no mergea.

## Siguiente paso

Los labels que disparan cada paso y las columnas del tablero están en [Labels y tablero](/ai-dev-team/guia/labels-y-tablero/).
