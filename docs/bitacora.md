# Bitácora del piloto

## 2026-10-03 y 04: configuración de GitHub
- Bot `maxiar-ai-dev-team-bot` creado, miembro de `maxiar-org` y colaborador con permiso de escritura en los repos.
- Token fine-grained con 90 días de vigencia. Vence aproximadamente el 2027-01-01; confirmar la fecha exacta en GitHub y renovarlo antes.
- Repos públicos `ai-dev-team` y `agent-playground`, con `main` protegida (exige PR y la aprobación de Eduardo).
- La organización exige aprobar los tokens fine-grained. Mientras el token estuvo pendiente de aprobación, solo podía leer, y el primer intento falló con 403.

## 2026-10-04: paso 0 (verificación de punta a punta)

| # | Comprobación del spec | Resultado |
|---|---|---|
| 1 | Canvas en `localhost:8000` | ✅ |
| 2 | Claude (Pro) y Codex (ChatGPT) por ACP; `flutter` y `gh` dentro de Canvas | ✅ |
| 3 | El bot clona el repo, crea la rama y abre el PR | ✅ |
| 4 | Issue → PR → review con el otro motor → métricas | ✅ issue #1 → PR #2 → `VEREDICTO: APROBADO` |
| 5 | El bot no puede mergear | ✅ no es admin; merge bloqueado sin la aprobación de Eduardo |

Tiempos: dev (Codex) 2,1 min, review (Claude) 1,1 min, unos 4,5 min en total desde el label hasta el pedido de review.

### Problemas encontrados y corregidos
- **API de Canvas abierta:** el entrypoint no exporta `OH_SESSION_API_KEYS_0` cuando se define `LOCAL_BACKEND_API_KEY`, así que la API aceptaba pedidos sin clave. Se agregó al compose; ahora responde 401 sin clave.
- **Login de Codex:** Canvas no lee `CODEX_AUTH_JSON` del entorno, solo como secreto de conversación o como `~/.codex/auth.json`. Se agregó `init-credentials.sh` y el volumen `codex-home`.
- **Certificados:** la imagen `node:22-slim` no trae `ca-certificates`, y los logins de Codex y Claude fallaban sin ellos.
- **Token de Claude:** se había pegado el código del navegador en lugar del token `sk-ant-oat01-…`.
- **Shell de login:** `flutter` no estaba en el PATH. Se agregaron symlinks en `/usr/local/bin`.

### Limitaciones de las métricas
- Para Codex, Canvas reporta costo 0 (no tiene precios para el modelo) y muy pocos tokens. El consumo real de Codex hay que mirarlo en la página de uso de ChatGPT.

## Pendiente para la fase 4 (mini-PC)
- **Probar las automatizaciones por eventos de Canvas.** Según https://docs.openhands.dev/enterprise/enterprise-vs-oss, Canvas en una VM las admite "si la VM es accesible", es decir, si GitHub puede llegar a ella desde internet. En self-hosted el camino es un webhook propio, porque el built-in de GitHub requiere la GitHub App y una organización de equipo de OpenHands Cloud. Prueba propuesta: Cloudflare Tunnel hacia Canvas, un webhook de GitHub en `agent-playground` y una automatización que se dispare con un label. Si funciona, el dispatcher recibe los eventos por webhook en lugar de consultar GitHub cada minuto.
