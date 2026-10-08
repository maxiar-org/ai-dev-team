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

## 2026-10-08: fase 4a cerrada (migración a la mini-PC, autonomía y operador remoto)
- **Todo corre en Docker Compose en la mini-PC** (`ubuntu-labs`, Ubuntu 26.04, 8 vCPU y 15 GB). En el host solo hay Docker. Servicios: `canvas`, `dispatcher`, `cloudflared`, `watchdog` y `operador`. La Mac ya no corre nada.
- **Acceso:** `canvas.maxiar.dev` por Cloudflare Tunnel, con Access (código por email). **Operador:** Claude Code con Remote Control (sesión "operador") y la cuenta de Eduardo, con `/estado` y `/desplegar`.
- **Criterios de éxito:**

  | # | Criterio | Resultado |
  |---|---|---|
  | 1 | Issue de prueba hasta el pedido de review, desde la mini-PC | ✅ agent-playground#3 → PR #4, QA OK |
  | 2 | Canvas desde el celular | ✅ (después de corregir el email en la política de Access) |
  | 3 | `/estado` desde la app de Claude | ✅ |
  | 4 | Alerta `[ops] dispatcher` en menos de 10 min y cierre automático | ✅ 7 min 40 s; cierre 105 s después de recuperarse |
  | 5 | Todo vuelve solo después de un reinicio | ✅ 5 servicios arriba en menos de 1 min, sin alertas falsas |

- **Problemas encontrados:**
  - `pilot/` sin permisos para el dispatcher en Linux: generó un bucle de cierre con labels yendo y viniendo unos 30 minutos. Se corrigió con permisos y con un fix de código (las métricas ya no traban el cierre). Las métricas de agent-playground#3 y #4 quedaron infladas unos 30 minutos.
  - Intervalo del watchdog: de 5 a 2 minutos, para cumplir los 10 minutos de detección.
  - `docker compose up -d watchdog` también levanta el dispatcher: hay que usar `--no-deps` (anotado para el operador).
  - Los tokens de Cloudflare y de Claude quedaron en el historial de la conversación: conviene rotarlos más adelante.
- **Vencimientos registrados:** token del bot el 2027-01-02 y token de Claude el 2027-10-04. El watchdog avisa 14 días antes.
- **Pendiente:** backups de la VM (`vzdump` en Proxmox).
- **Siguiente:** 4b (Coolify y previews), 4c (eventos de GitHub) y 4d (vista de estado).

## 2026-10-08: fase 4b cerrada (Coolify y previews por PR)
- **Coolify 4.4.2** en `/data/coolify` (segundo proyecto Compose). Panel en `coolify.maxiar.dev`, con Access y bypass para `/webhooks`. Todos sus puertos están en `127.0.0.1` (`docker-compose.custom.yml` más el proxy editado). Las apps se crean por la API de Coolify (`COOLIFY_API_TOKEN` en `.env`).
- **Criterios de éxito:**

  | # | Criterio | Resultado |
  |---|---|---|
  | 1 | Prueba acotada `preview-lab` (compose con app, Postgres y Redis) | ✅ estable en `preview-lab.maxiar.dev`; la preview `preview-lab-pr-1` con su propia base (el contador arrancó en 1 contra 8 en `main`); link en el PR; limpieza en 10 s |
  | 2 | `qr.maxiar.dev` sirve `main` | ✅ |
  | 3 | Previews de `qr-generator` | ✅ `qr-pr-23` en 123 s, con Access, link en el PR y limpieza en 10 s |
  | 4 | Nada de Coolify en la LAN | ✅ |
  | 5 | `[ops] coolify` | ✅ alerta en 147 s; `qr.maxiar.dev` siguió respondiendo 200 con Coolify caído; cierre automático 104 s después de levantarlo |

- **Problemas encontrados y resueltos:**
  - El panel de Coolify chocaba con Canvas en el puerto 8000 → pasó al `127.0.0.1:8100` con `docker-compose.custom.yml`.
  - El dominio de Coolify estaba vacío, así que la GitHub App quedó con el webhook apuntando a una URL local → se configuró `https://coolify.maxiar.dev` y se corrigió la URL del webhook en GitHub.
  - **Membresía privada en la organización:** Coolify ignora sin error los PRs cuyo autor no aparece como miembro. La membresía de Eduardo ya es pública; **falta la del bot** (requiere su login web; hay que recuperar su contraseña y activarle el 2FA).
  - **Previews de compose:** los servicios se renombran a `<svc>-pr-N`, y la app tiene que leer `SERVICE_NAME_<SVC>` en tiempo de ejecución (documentado en el README).
  - Access no acepta dos comodines en un nombre → una aplicación de Access por proyecto.
- **Tokens a rotar:** se pegaron en la conversación el `TUNNEL_TOKEN`, el `CLAUDE_CODE_OAUTH_TOKEN` y el `COOLIFY_API_TOKEN`.
- **Siguiente:** 4c (eventos de GitHub) y 4d (vista de estado). QA sobre las previews queda para cuando haya un proyecto con base de datos.
