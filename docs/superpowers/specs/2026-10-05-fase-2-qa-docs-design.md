# Fase 2: roles QA y Docs, diseño

- **Fecha:** 2026-10-05
- **Autor:** Eduardo Jiménez (con Claude)
- **Estado:** aprobado en conversación, pendiente de revisión escrita
- **Antecedentes:** `pilot/REPORT.md` (piloto cerrado) y `docs/superpowers/specs/2026-10-03-ai-dev-team-pilot-design.md`

## 1. Objetivo

Sumar al equipo dos roles nuevos, con tareas básicas, y dejar el framework listo para la fase 4 (migración a la mini-PC):

- **QA:** prueba el **comportamiento** de la app con Playwright antes de que un PR llegue a Eduardo.
- **Docs:** documenta, en un sitio con índice, búsqueda y buena UI (Starlight), tanto el proyecto como el framework.

No se suma un segundo proyecto: `qr-generator` ya es un proyecto real.

### Criterios de éxito

1. Un PR de UI en `qr-generator` recorre dev → reviewer → QA → Eduardo sin intervención, y el QA deja capturas y un veredicto.
2. Un `QA: FALLA` vuelve al dev, que lo corrige, y el PR vuelve a pasar por review y por QA.
3. Hay dos sitios Starlight publicados en GitHub Pages, creados por el rol de docs:
   - `maxiar-org.github.io/qr-generator/`, con la guía de uso para Maxi y la arquitectura;
   - `maxiar-org.github.io/ai-dev-team/`, con cómo funciona el equipo y las lecciones del piloto.
4. En `ai-dev-team`, los agentes solo pueden tocar documentación.

## 2. Responsabilidades separadas

| Rol | Qué mira | Cómo | Navegador | Motor por defecto |
|---|---|---|---|---|
| Dev | Implementar | TDD, analyze y tests | No | Codex (`engine:*` en el issue) |
| Reviewer | **El código**: criterios de aceptación contra el diff, bugs, diseño, calidad de los tests, regresiones en el código (rutas, pantallas o campos eliminados o desconectados) y estado del CI | Diff y tests | No | El otro motor del dev |
| **QA** | **El comportamiento**: la app como la usaría la persona usuaria | Compila y sirve la app según `AGENTS.md`, arma un plan de prueba (criterios del issue + "flujos principales"), lo ejecuta con Playwright y toma capturas | Sí, solo él | `QA_ENGINE` (por defecto `codex`) |
| **Docs** | La documentación del repo del issue | Edita el sitio Starlight en `docs/` | Opcional | `DOCS_ENGINE` (por defecto `claude`) |
| Fix | Atiende `VEREDICTO: CAMBIOS`, `QA: FALLA`, conflictos o pedidos de Eduardo | TDD | No | El del dev |

## 3. Flujo

```
issue + agent:dev   → DEV  ─┐
issue + agent:docs  → DOCS ─┤→ PR (agent:review + engine:<motor>)
                            ▼
                      REVIEWER ── CAMBIOS ──► agent:fix → FIX → agent:review
                            │ APROBADO
                            ▼
                      agent:qa → QA ── FALLA ──► agent:fix → FIX → agent:review → … → QA
                            │ OK o N/A
                            ▼
                      pedido de review a Eduardo
```

- **Límites:**
  - Máximo **2 rondas de review** (contador actual) y **2 rondas de QA** (contador nuevo `qa_rounds` por PR). Al pasar el máximo, `needs:human`.
  - Sin veredicto reconocible → `needs:human`.
- **Fix:** el fix disparado por label vuelve a `agent:review`, como hoy, y el reviewer, si aprueba, vuelve a mandar a QA.
- **Veredicto de QA:** se lee con `QA:\s*\**\s*(OK|FALLA|N/A)` y se toma el último. `N/A` es para PRs sin cambios visibles, por ejemplo uno que solo cambia documentación de texto.
- **Fix por pedido de Eduardo** (`@openhands`): sigue igual, le vuelve a pedir review a él.

## 4. Dispatcher: cambios

| Componente | Cambio |
|---|---|
| `models` | Rol `qa` y rol `docs`. Labels `agent:qa` y `agent:docs` |
| `config` | `QA_ENGINE` (por defecto `codex`), `DOCS_ENGINE` (por defecto `claude`), `DOCS_ONLY_REPOS` (lista, por defecto vacía) |
| `decide` | Candidatos nuevos: issue con `agent:docs` → `docs`; PR con `agent:qa` → `qa`. En un repo de `DOCS_ONLY_REPOS`, un issue con `agent:dev` no arranca y se avisa una vez (acción `DocsOnlyNotice`). Las dependencias (`Depende de`) también aplican a `docs` |
| `outcomes` | Review `APROBADO` → `AddLabels(agent:qa)` (antes era `RequestReview`). QA `OK` o `N/A` → `RequestReview`. QA `FALLA` → `agent:fix` y suma una ronda de QA; si pasa el máximo, `needs:human`. QA sin veredicto → `needs:human`. Docs → igual que dev: si hay PR, `agent:review` + `engine:<motor>` |
| `state` | `qa_rounds: dict[str, int]` y `docs_only_notified: set[str]` |
| `board` | `agent:qa` → columna "En review" (no hace falta tocarlo: los PRs ya van ahí) |
| `prompts` | `ROLE_FILES` agrega `qa: qa.md` y `docs: docs.md` |

## 5. Roles (plantillas)

- **`roles/dev.md`:** se quita el paso de verificación con Playwright.
- **`roles/reviewer.md`:** se quita el recorrido con Playwright. Se mantiene "las regresiones en el código son bloqueantes". Se agrega: en los repos de solo documentación, cualquier cambio fuera de `docs/` y de los `.md` es bloqueante.
- **`roles/fix.md`:** atiende el último comentario con `VEREDICTO: CAMBIOS` **o** `QA: FALLA`.
- **`roles/qa.md` (nuevo):**
  1. Compila y sirve la app según la sección "Probar la UI" de `AGENTS.md`.
  2. Escribe un plan de prueba numerado.
  3. Lo ejecuta con Playwright.
  4. **Evidencia:** sube las capturas a la rama huérfana `qa-evidence`, en `pr-<n>/<ronda>/`, creándola si no existe, y las enlaza con URLs `raw.githubusercontent.com` en un único comentario.
  5. Cierra con `QA: OK`, `QA: FALLA` (cada falla con pasos para reproducirla, resultado esperado y resultado obtenido) o `QA: N/A`.
  6. No modifica el código del PR.
- **`roles/docs.md` (nuevo):**
  - Trabaja en `docs/` del repo, con Starlight.
  - Si el sitio no existe, lo crea (Astro + Starlight, en español, búsqueda, sidebar autogenerado) junto con el workflow de deploy a GitHub Pages con el `base` correcto (`/<repo>/`).
  - Escribe en español rioplatense, claro, con ejemplos y diagramas Mermaid cuando sirvan.
  - Abre el PR con el link al sitio como entregable visible.

## 6. `ai-dev-team` como repo atendido

- Se suma a `REPOS` y a `DOCS_ONLY_REPOS`. Se sincronizan los labels y se copia la plantilla de issue.
- Recibe su propio `AGENTS.md`, con la regla de solo documentación, los comandos de Starlight (`npm ci`, `npm run build`, `npm run preview`) y la sección "Probar la UI" del sitio de docs, para el QA.
- El bot ya tiene permiso de escritura y `main` ya está protegida.
- `qr-generator/AGENTS.md`: sin cambios funcionales. Ya tiene "Probar la UI" y "Flujos principales".

## 7. Primeros issues (estreno de los roles)

1. **`qr-generator`** (`agent:docs`): sitio Starlight en `docs/` con deploy a GitHub Pages. Páginas: inicio, guía de uso para Maxi (cada tipo de QR, imprimir con WePrint, instalar en el iPhone), arquitectura de la app y decisiones (Reseñas, Mercado Pago, impresión directa), enlazando los documentos existentes.
2. **`ai-dev-team`** (`agent:docs`): sitio Starlight en `docs/` con deploy a GitHub Pages. Páginas: qué es y cómo funciona el equipo (diagrama del flujo), roles, labels, cómo sumar un proyecto, operación (arrancar, credenciales, métricas) y lecciones del piloto (resumen de `pilot/REPORT.md`). Los specs y planes existentes en `docs/superpowers/` quedan fuera del sidebar.

Antes de que corran, Eduardo (o Claude con su `gh`) activa GitHub Pages en los dos repos con origen **GitHub Actions**.

## 8. Tests

- **`decide`:** candidatos de `docs` y de `qa`, `DOCS_ONLY_REPOS` (no arranca y avisa una sola vez) y dependencias en `docs`.
- **`outcomes`:**
  - review `APROBADO` → `agent:qa`;
  - QA `OK` y `N/A` → `RequestReview`;
  - QA `FALLA` → `agent:fix` y contador; pasado el máximo → `needs:human`;
  - QA sin veredicto → `needs:human`;
  - parseo de las variantes del veredicto de QA;
  - docs con PR → review.
- **`config`:** las variables nuevas y sus valores por defecto.
- **`runner`:**
  - ciclo dev → review → QA OK → pedido de review;
  - ciclo QA FALLA → fix → review → QA;
  - `docs` en un repo de solo documentación.
- **`prompts`:** `qa.md` y `docs.md` sin marcadores sin reemplazar, con sus veredictos y reglas.

## 9. Fuera de alcance

- Changelog automático después de cada merge (próxima fase).
- Previews por PR, eventos de Canvas y migración a la mini-PC (fase 4).
- Una suite E2E con Playwright en el CI (posible tarea futura del QA).

## 10. Riesgos

| Riesgo | Mitigación |
|---|---|
| QA suma una conversación por PR | Codex por defecto (rápido y barato). `N/A` para PRs sin cambios visibles |
| La rama `qa-evidence` crece con imágenes | Las capturas son livianas; si hace falta, se purga en la fase 4 |
| El agente de docs toca código en `ai-dev-team` | `DOCS_ONLY_REPOS` en el dispatcher + regla bloqueante del reviewer + aprobación de Eduardo |
| El deploy de Pages falla por el `base` de Astro | El QA verifica el sitio publicado; las instrucciones del rol exigen `base: '/<repo>/'` |
