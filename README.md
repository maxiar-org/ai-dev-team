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
| — | Si hay `VEREDICTO: APROBADO`, te llega un pedido de review en GitHub |
| Comentas `@openhands ...` en un issue o PR | El dev retoma la tarea con tu instrucción |
| Ves `needs:human` | Un agente necesita una decisión tuya: respóndele con `@openhands ...` |
| Apruebas y mergeas | Solo tú puedes hacerlo; `main` está protegida |

Para ver el trabajo en vivo, abre http://localhost:8000/canvas (pide la `CANVAS_API_KEY`).

## Arrancar

```bash
cp .env.example .env        # completar (ver Credenciales)
docker compose up -d --build
docker compose logs -f dispatcher
```

## Credenciales

- **Claude (cuenta Pro del piloto):**
  1. En una ventana de incógnito, con sesión iniciada **solo** en la cuenta Pro, ejecuta:
     `docker run --rm -it node:22-slim sh -c "npm i -g @anthropic-ai/claude-code >/dev/null && claude setup-token"`
  2. Abre la URL que imprime en esa ventana.
  3. Pega el token en `CLAUDE_CODE_OAUTH_TOKEN`. Dura 1 año.
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

- **Codex deja de autenticar después de reiniciar el contenedor:** el `auth.json` de `.env` puede haber rotado. Regenéralo (ver Credenciales).
- **En la mini-PC (Linux), `./pilot` tiene que poder escribirlo el UID 10001:** `sudo chown 10001:10001 pilot`.
