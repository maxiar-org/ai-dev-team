# AI Dev Team

Equipo de agentes de IA (dev y reviewer) que trabaja sobre los repos de `maxiar-org`:
toma issues etiquetados, abre PRs, los revisa con otro modelo y te pide la aprobación final.

- **Diseño:** `docs/superpowers/specs/2026-10-03-ai-dev-team-pilot-design.md`
- **Plan:** `docs/superpowers/plans/2026-10-03-ai-dev-team-pilot.md`

## Cómo funciona

| Tú haces | Qué pasa |
|---|---|
| Pones `agent:dev` en un issue | El dev (Codex por defecto; `engine:claude` lo cambia) implementa con TDD y abre un PR |
| — | El dispatcher le pone `agent:review` al PR y lo revisa el otro modelo |
| — | Si hay `VEREDICTO: CAMBIOS`, el dev corrige (máximo 2 rondas) |
| — | Si hay `VEREDICTO: APROBADO`, el PR pasa a **QA** (Codex), que prueba la app con Playwright: `QA: OK` → te llega un pedido de review; `QA: FALLA` → vuelve al dev |
| Pones `agent:docs` en un issue | El agente de docs (Claude por defecto) actualiza el sitio Starlight del repo y abre un PR |
| Comentas `@openhands ...` en un issue o PR (comentario normal o review del PR; no en comentarios sobre líneas de código) | El dev retoma la tarea con tu instrucción |
| — | Si un PR queda con conflictos con `main` (por ejemplo, después de mergear otro), el dev los resuelve solo (máximo 2 intentos) y el PR vuelve a review y QA |
| Escribes `Depende de #N` en un issue | El dispatcher no lo arranca hasta que el #N se cierre, y lo avisa con un comentario |
| Ves `needs:human` | Un agente necesita una decisión tuya: respóndele con `@openhands ...` |
| Apruebas y mergeas | Solo tú puedes hacerlo; `main` está protegida |

Para ver el trabajo en vivo, abre http://localhost:8000/canvas (pide la `CANVAS_API_KEY`).

Para ver el estado general, usa el **tablero** https://github.com/orgs/maxiar-org/projects/1. El dispatcher agrega cada issue y PR de los repos en `REPOS` y lo mueve de columna según sus labels: Backlog → Listo para agentes → En curso → En review / Necesita a Eduardo. La columna Hecho la pone la automatización nativa del tablero al cerrar o mergear.

## Arrancar

```bash
cp .env.example .env        # completar (ver Credenciales)
docker compose up -d --build
docker compose logs -f dispatcher
```

## Credenciales

- **Claude (cuenta Pro del piloto):**
  1. En una ventana de incógnito, con sesión iniciada **solo** en la cuenta Pro, ejecuta:
     `docker run --rm -it node:22-slim sh -c "apt-get update -qq >/dev/null && apt-get install -y -qq ca-certificates >/dev/null && npm i -g @anthropic-ai/claude-code >/dev/null && claude setup-token"`
  2. Abre la URL que imprime en esa ventana.
  3. El navegador muestra un **código**: pégalo de vuelta en la terminal.
  4. La terminal imprime el token final (`sk-ant-oat01-…`). Ese va en `CLAUDE_CODE_OAUTH_TOKEN`. Dura 1 año.
- **Codex (ChatGPT):**
  1. Habilita el login por código de dispositivo en la configuración de seguridad de ChatGPT.
  2. Ejecuta (la imagen slim no trae certificados raíz, por eso se instala `ca-certificates`):
     `docker run --rm -it -v "$PWD:/out" node:22-slim sh -c "apt-get update -qq >/dev/null && apt-get install -y -qq ca-certificates >/dev/null && npm i -g @openai/codex >/dev/null && codex login --device-auth && node -e 'process.stdout.write(JSON.stringify(require(\"/root/.codex/auth.json\")))' > /out/codex_auth.json"`
  3. Copia el contenido de `codex_auth.json` en `CODEX_AUTH_JSON` y borra el archivo: `rm codex_auth.json`.
- **Respaldo pagado (API de Anthropic, tope USD 100):**
  1. Agrega `ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}` al servicio `canvas` del compose.
  2. Agrega la clave en `.env` **y vacía** `CLAUDE_CODE_OAUTH_TOKEN`.
  3. Ejecuta `docker compose up -d`.

## Operación

- **Métricas:** `pilot/metrics.csv`.
- **Resumen:** `docker compose run --rm dispatcher report`.
- **Agregar un proyecto:**
  1. Ejecuta `scripts/sync-labels.sh maxiar-org/<repo>`.
  2. Copia `github/ISSUE_TEMPLATE/agent-task.md` a `.github/ISSUE_TEMPLATE/` del repo.
  3. Agrega el repo a `REPOS` en `.env`.
  4. Ejecuta `docker compose up -d`.
- **Una tarea quedó trabada en `agent:working`:** revisa la conversación en Canvas. Si hace falta, quita el label a mano y borra la tarea de `state.json`: `docker compose exec dispatcher sh`, archivo `/state/state.json`.

## Problemas conocidos

- **Codex deja de autenticar:** el login vive en el volumen `codex-home` y se crea desde `CODEX_AUTH_JSON` solo la primera vez. Para usar un login nuevo: actualiza `.env`, ejecuta `docker compose down`, luego `docker volume rm ai-dev-team_codex-home`, y por último `docker compose up -d`.
- **En Linux, `./pilot` tiene que poder escribirlo el dispatcher (UID 10001) y el usuario `aidev`:** `sudo chown -R 10001:$(id -g aidev) pilot && sudo chmod 2775 pilot && sudo chmod 664 pilot/*`.

## Mini-PC y operador

Todo corre en Docker Compose en la mini-PC. En el host solo está Docker.

- **Entrar:** `ssh ubuntu-labs`, después `sudo -iu aidev`, y `cd /opt/ai-dev-team`.
- **Estado de todo:** https://estado.maxiar.dev (Access). Arriba, qué espera de vos y en qué orden mergear; abajo, el trabajo en curso, los despliegues y previews, la salud y el consumo. Se actualiza cada minuto, sin LLM (servicio `estado`). El botón **"Pedir resumen"** le pide al operador (con `claude -p` y tu cuenta personal) qué pasó desde el resumen anterior y qué hacer y por qué; tarda de 1 a 3 minutos y los resúmenes quedan en `~/resumenes` del volumen `operador-home`.
- **Ver a los agentes:** https://canvas.maxiar.dev (login de Cloudflare Access con tu email).
- **Hablar con el operador:** en la app de Claude o en claude.ai/code, abre la sesión de Remote Control **"operador"**. Es Claude Code corriendo en la mini-PC, con el conocimiento de `CLAUDE.md` y los skills `/estado` y `/desplegar`.
- **Primer login del operador:** `docker compose exec -it operador claude` (login por código con tu cuenta personal) y después `docker compose restart operador`. Para `gh`: `docker compose exec -it operador gh auth login` y luego `docker compose exec -it operador gh auth refresh -s read:project` (para leer el tablero).
- **Instrucciones del operador:** viven en `operador/claude/` (`CLAUDE.md` y skills) y se copian a su HOME cada vez que arranca. No van en la raíz del repo, para que no las lean los agentes.
- **Alertas:** el `watchdog` abre issues `[ops]` en `ai-dev-team` si se cae Canvas, el dispatcher, el túnel o el disco pasa el 85 %, y los cierra solo cuando se recuperan. También avisa 14 días antes de que venzan los tokens (`GITHUB_TOKEN_EXPIRES`, `CLAUDE_TOKEN_EXPIRES`).
- **Mudar a otra máquina:** instalar Docker, copiar el repo **exactamente en `/opt/ai-dev-team`**, el `.env` y los volúmenes, y ejecutar `docker compose up -d`. La ruta es fija porque el operador ejecuta `docker compose` desde su contenedor y el daemon del host resuelve los bind mounts con esa ruta. Después, aplica los permisos de `pilot/` (ver Problemas conocidos).

## Coolify y previews

Coolify (instalado en `/data/coolify`, con su panel en https://coolify.maxiar.dev detrás de Access) despliega cada proyecto:
- **Versión estable:** `https://<proyecto>.maxiar.dev`, que se redespliega en cada merge a `main`.
- **Previews por PR:** `https://<proyecto>-pr-N.maxiar.dev`, detrás de Access. Se crean al abrir el PR y se borran al cerrarlo.

**Sumar un proyecto:**
1. En Coolify, crea la aplicación desde la GitHub App, con el build pack Dockerfile o Docker Compose.
2. Ponle el dominio `http://<p>.maxiar.dev` y activa Preview Deployments con la URL `http://<p>-pr-{{pr_id}}.maxiar.dev`.
3. Si el comodín general de Access no cubre el proyecto, crea en Cloudflare Access la aplicación `<p>-pr-*.maxiar.dev`.

**Reglas aprendidas en la prueba acotada (fase 4b):**
- **Servicios en previews de compose:** Coolify los renombra a `<servicio>-pr-N`. La interpolación del compose (`${...}`) **no** ve el nombre nuevo, así que la app tiene que leer en tiempo de ejecución las variables que inyecta Coolify, `SERVICE_NAME_<SERVICIO>` (por ejemplo `SERVICE_NAME_POSTGRES`), con el nombre normal como valor por defecto. Ejemplo en `maxiar-org/preview-lab` (`app.py`).
- **Autores de PRs:** Coolify solo despliega previews de PRs cuyo autor figura como `OWNER`, `MEMBER` o `COLLABORATOR`. La membresía en `maxiar-org` de Eduardo y del bot tiene que ser **pública**; si no, los PRs se ignoran sin dejar error.
- **Access:** no acepta dos comodines en un nombre (`*-pr-*`), así que se crea una aplicación de Access por proyecto: `<p>-pr-*`.
- **Puertos de Coolify:** se definen en `/data/coolify/source/docker-compose.custom.yml` (Coolify lo incluye en cada actualización) y en `/data/coolify/proxy/docker-compose.yml` (proxy en `127.0.0.1`).

**Mudanza:** copia `/data/coolify` a la máquina nueva y corre el instalador oficial; los puertos de Coolify van solo en `127.0.0.1`.

