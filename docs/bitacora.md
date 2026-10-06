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
- **Complemento visual propio para ai-dev-team.** Una vista de estado y resumen por proyecto: qué está hecho, qué está en curso, qué está bloqueado, qué espera a Eduardo y en qué orden mergear, más las métricas de consumo. Hoy ese resumen lo arma Claude Code cuando Eduardo lo pide, y complementa al Kanban de GitHub Projects. Hay que evaluarlo junto con el approach de eventos.

## Decisiones de arquitectura (2026-10-05)
- **Rol de OpenHands:** se usa solo como runtime de agentes (ejecución ACP con suscripciones, entorno de trabajo, historial de conversaciones y métricas de tokens). La orquestación es propia, en el dispatcher.
- **OpenHands Cloud Individual descartado por ahora:** tiene un límite de 10 conversaciones por día y solo funciona con API key o créditos (pago por uso), sin las suscripciones.

## Fase 4: previews por PR (eje propuesto, 2026-10-05)
Necesidad: probar los entregables visuales sin tener que clonar, compilar ni estar frente a la máquina. Para proyectos futuros, eso incluye el stack completo (app, DB, caché, monitoreo).

| Opción | Resumen | Evaluación |
|---|---|---|
| **A. PaaS self-hosted en la mini-PC (Coolify o Dokploy) + Cloudflare Tunnel** | Preview por PR desde el `docker-compose` completo, en `pr-N.<proyecto>.<dominio>` con HTTPS, que se borra al cerrar el PR | **Recomendada.** Cero código propio y costo cero (solo el dominio). El mismo túnel destraba los eventos de Canvas, y trae su propio panel de despliegues |
| B. Nube con contenedores (Cloud Run, Fly.io, Railway) | El CI arma la imagen, la sube a GHCR y despliega una revisión por PR | No depende del hardware, pero las bases de datos por preview cuestan y hay más configuración |
| C. Runner self-hosted + compose a mano | Igual que A, pero construido a mano | Reinventa lo que A ya trae |

Es una decisión de arquitectura: necesita su propio diseño, spec y plan. Se evalúa junto con los eventos de Canvas y el complemento visual.

Solución temporal para el piloto: `cloudflared tunnel --url` desde la Mac, que da una URL HTTPS `*.trycloudflare.com` sin cuenta y dura mientras corre el comando.

## 2026-10-05: fase 2 cerrada (roles QA y Docs)
- **Flujo nuevo:** dev → reviewer (código) → **QA** (comportamiento, con Playwright y capturas en la rama `qa-evidence`) → Eduardo. Un `QA: FALLA` vuelve al dev. El reviewer y el dev ya no usan el navegador.
- **Rol Docs:** se dispara con `agent:docs` y escribe un sitio Starlight publicado en GitHub Pages. `ai-dev-team` se atiende como repo de solo documentación.
- **Estreno:**
  - `ai-dev-team#1` → PR #2. Docs con Claude en 26 min, review y QA OK a la primera. Publicado en https://maxiar-org.github.io/ai-dev-team/
  - `qr-generator#21` → PR #22. **QA detectó que el diagrama Mermaid era ilegible en el celular** (`QA: FALLA` con medición y captura). Lo corrigió el fix y la segunda ronda dio `QA: OK`. QA también corrió una regresión de WhatsApp e Instagram decodificando los QR. Publicado en https://maxiar-org.github.io/qr-generator/
- **La revisión independiente encontró dos problemas importantes antes del despliegue** (el reviewer bloqueaba el workflow de docs, y los comandos de evidencia de QA eran frágiles en el contenedor compartido). Se corrigieron con tests.
- **Pendientes post-piloto en `qr-generator`:** #8 (impresión directa, `needs:human`), #19 (Place ID automático) y #20 (escanear el QR de Mercado Pago).
- **Siguiente:** fase 4, la migración a la mini-PC.
