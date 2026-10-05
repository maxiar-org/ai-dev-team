# AGENTS.md: ai-dev-team

Este repo es el framework del AI Dev Team: el dispatcher (Python), las plantillas de roles, Docker y la documentación.

## ⚠️ Repo de solo documentación
Los agentes **solo** pueden modificar `docs/` (sitio Starlight), archivos `.md` y `.github/workflows/docs.yml`. El código del dispatcher, `roles/`, Docker y la configuración los cambian Eduardo y Claude Code. Cualquier cambio fuera de eso es bloqueante en la review.

## Documentación (Starlight)
- El sitio vive en `docs/` (contenido en `docs/src/content/docs/`) y se publica en https://maxiar-org.github.io/ai-dev-team/.
- `docs/superpowers/` (specs y planes) y `docs/bitacora.md` son documentos de trabajo: no se mueven ni se borran. Se pueden enlazar desde el sitio.
- Verificación antes del PR: `cd docs && npm ci && npm run build`.

## Probar la UI
```bash
cd docs && npm ci && npm run build && npx astro preview --port 8765 --host 0.0.0.0 >/dev/null 2>&1 &
```
Abre `http://localhost:8765/ai-dev-team/` y recorre el índice, la búsqueda y cada página nueva.

## Convenciones
- Español rioplatense, claro, con ejemplos. Diagramas Mermaid para los flujos.
- Ramas `agent/<issue>-<slug>`. Un PR por issue, con `Closes #<issue>` y la sección **Entregable visible**.
