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

## 2026-10-08: fase 4d cerrada (vista de estado)
- **`estado.maxiar.dev`** (Access): servicio `estado` del compose, con la misma imagen del dispatcher. Junta datos cada 60 s (GitHub, `state.json`, `metrics.csv`, Coolify y los chequeos del watchdog) y arma la página con reglas fijas, sin LLM.
- **Criterios de éxito:**

  | # | Criterio | Resultado |
  |---|---|---|
  | 1 | Abre en el celular detrás de Access, con las cuatro secciones | ✅ la URL pública redirige al login de Access (302); las secciones se ven con datos reales |
  | 2 | PRs para revisar y `needs:human` arriba, con links y orden de merge | ✅ `qr-generator #8` (`needs:human`) arriba, con el último comentario del bot; el orden de merge está cubierto por tests (hoy no hay PRs esperando) |
  | 3 | Se actualiza sola, con datos de menos de 2 minutos | ✅ "actualizado hace 30 a 63 s" |
  | 4 | Una fuente caída no tira la página | ✅ con Coolify apagado: "Despliegues" mostró "sin datos", el chequeo de salud de Coolify dio FALLA y el resto siguió igual; se recuperó solo |
  | 5 | Cero LLM | ✅ |

- **Revisión final:** encontró 7 hallazgos importantes, todos corregidos con tests (202 en total):
  - el PR de un issue que todavía está en dev no aparece como "para revisar";
  - solo `dirty` cuenta como conflicto;
  - el orden de merge y los avisos de archivos se calculan por repo;
  - con GitHub caído nunca dice "Nada pendiente";
  - se pide el detalle solo de los PRs que pueden esperar a Eduardo, para cuidar el límite de la API.
- **Membresía del bot:** Eduardo la hizo pública. Queda pendiente rotar los tokens y activarle el 2FA al bot.
- **Siguiente:** el botón "Resumen del operador" a pedido (opción C), y la fase futura de mejoras.

## 2026-10-09: fase 4e cerrada (resumen del operador a pedido)
- **Botón "Pedir resumen"** en `estado.maxiar.dev`: el operador (`claude -p` con la cuenta de Eduardo) escribe "Qué pasó" desde el resumen anterior y "Qué hacer y por qué". `estado` junta los datos del período sin LLM y los manda por la red interna `resumen`, con token. Los resúmenes quedan en `~/resumenes` del volumen `operador-home`.
- **Criterios de éxito:**

  | # | Criterio | Resultado |
  |---|---|---|
  | 1 | Resumen en 3 minutos o menos, con fecha y período | ✅ unos 30 s; 309 palabras; Eduardo lo encontró "útil y preciso" |
  | 2 | El segundo cubre solo desde el primero | ✅ el segundo cubre desde las 01:03:18Z, la hora del primero |
  | 3 | "generando…" sin permitir otro pedido | ✅ lo cubren tests; además hay una pausa mínima de 120 s |
  | 4 | Con el operador caído, la página sigue | ✅ `estado` muestra el error; el servidor se relanza solo en menos de 8 s (después del arreglo del PR #9) |
  | 5 | Los agentes no llegan; `claude -p` no escribe ni usa `docker` ni lee archivos | ✅ desde Canvas, `estado` y el operador no resuelven ni conectan; el log del filtro muestra bloqueados `docker ps`, la comprobación del `.env`, `echo` y `gh api` |

- **Seguridad:**
  - Una prueba real mostró que `claude -p`, en modo `dontAsk`, aprueba por su cuenta comandos que considera de lectura (`docker ps`). Por eso la lista blanca efectiva es nuestro hook `PreToolUse` (`operador/resumen_guard.py`): solo `gh issue|pr|run` de lectura sobre `maxiar-org`, sin metacaracteres. Cada decisión queda en `~/resumenes/guard.log`.
  - En el uso real, el operador intentó comandos compuestos (`--jq` y `;`), el filtro los bloqueó y siguió con comandos simples.
  - `estado` ahora escucha solo en la red `publico`, compartida con `cloudflared`; la ruta del túnel apunta a `estado-publico:8090`.
- **Problemas encontrados en el despliegue y resueltos:**
  - GitHub exige `is:issue` o `is:pr` en la búsqueda: la de `[ops]` daba 422 (PR #8).
  - `set -e` de `start.sh` cortaba el bucle que relanza el servidor (PR #9).
- **Siguiente:** la fase futura de mejoras.

## 2026-10-09: skills para los agentes
- **Hallazgo:** cada motor lee una sola ruta de skills. Claude (`claude-agent-acp` 0.63) lee `.claude/skills` y Codex (`codex-acp`) lee `.agents/skills`. Con `.claude/skills` como enlace simbólico a `../.agents/skills`, los dos ven la misma copia. Lo verificamos con skills señuelo en Canvas.
- **Convención:** las skills van en el repo del proyecto, se instalan por PR y sin hooks. El procedimiento está en el README ("Skills para los agentes").
- **Primeras skills:** `frontend-design` (Anthropic) e `impeccable` 4.5.1 en qr-generator (qr-generator#25), para un issue de diseño. Son skills pensadas para web, aplicadas a Flutter como experimento.

## 2026-10-09: generación de imágenes
- **Prueba de factibilidad:** Codex en Canvas generó un ícono de 1254×1254 con la skill de sistema `imagegen` en modo herramienta integrada. Usó la suscripción de ChatGPT, sin `OPENAI_API_KEY`.
- **Decisión:** por ahora alcanza con esta capacidad, y las tareas de imágenes van con `engine:codex`. Lo que no cubra (video, volumen o calidad) queda para `mcp-image`, que trabaja con APIs pagas.
- **Primer uso:** el logo de qr-generator, y de ahí el favicon, los íconos de la app y la estructura de app (cabecera, menú, pantalla de carga e instalación en el celular).

## Fase futura de mejoras (backlog)
- **4c, eventos de GitHub por webhook** (en lugar del polling cada 60 s): se posterga por decisión de Eduardo (2026-10-08), porque la latencia actual no molesta. Hay base para hacerlo: el túnel y los webhooks ya funcionan con Coolify.
- **Gemini como tercer motor, para QA y review** (idea de Eduardo, 2026-10-10; para analizar):
  - **Por qué:** hoy el reviewer es "el otro motor" y bloquea a ese motor para programar. Con Gemini en QA y review, Claude y Codex quedan libres para programar. Además, Gemini es fuerte comparando imágenes, útil para la fidelidad a los mockups en nikito.
  - **Por qué no como dev:** la Fase 1 de nikito es casi una cadena de dependencias, y el cuello de botella son las revisiones y los merges de Eduardo. Se reevalúa si aparecen muchas tareas independientes (Fases 2 y 3).
  - **Escalonado:**
    1. Solo QA (`qa_engine` ya es configurable), probado con 3 o 4 PRs de nikito y comparado con el QA actual.
    2. Después, reviewer: `other_engine` hoy es binario y habría que generalizarlo.
  - **Regla:** **las decisiones de arquitectura las toma siempre Claude.**
    - Los ADR los escribe Claude Code al planificar, o van como issues con `engine:claude`.
    - El reviewer y el QA de otro motor no deciden arquitectura: si ven un problema de diseño, marcan `needs:human`.
  - **A verificar:**
    - que Gemini CLI funcione por ACP dentro de Canvas;
    - que el login con la suscripción Gemini Pro persista en el contenedor;
    - que los términos de la suscripción permitan este uso automatizado.
- **QA sobre las previews desplegadas** (service token de Access), cuando haya un proyecto con base de datos.
- **Resumen del operador, ideas:** un resumen programado (por ejemplo, cada mañana) e historial navegable.
- **Resumen del operador, menores:**
  - el `?error=` muestra texto libre (escapado): conviene usar códigos;
  - un timeout de `claude` puede dejar procesos hijos huérfanos (los recoge `init`);
  - si el alias de red no resuelve al arrancar, se reintenta cada 5 s con trazas en los logs.
- **Vista de estado, menores:**
  - si no hay token de Coolify, "Despliegues" aparece vacía sin explicar por qué;
  - con `take=30`, la preview de un PR abierto hace mucho puede quedar fuera del historial de Coolify;
  - un PR huérfano con `agent:working` aparece como "espera a Eduardo";
  - faltan los estados de CI `action_required` y `neutral`;
  - los logs de httpx en nivel INFO llenan los logs (unas 20 líneas por minuto).
- **Dispatcher, PR mergeado durante una tarea:** si Eduardo mergea un PR mientras corre el fix, la tarea sigue y al terminar le pone `agent:review` a un PR ya cerrado. Pasó con nikito#15 y se resolvió a mano: se reabrió el issue y se abrió el PR #16 desde la misma rama. Conviene detectar el merge y avisar, o abrir el PR de seguimiento solo.
- **Mejoras menores diferidas** de las revisiones de código (ver ledgers y bitácoras de cada fase).
