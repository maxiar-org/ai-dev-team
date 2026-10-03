# AI Dev Team: diseño del piloto (fase 1)

- **Fecha:** 2026-10-03
- **Autor:** Eduardo Jiménez (con Claude)
- **Estado:** pendiente de revisión

## 1. Contexto y objetivo

Eduardo trabaja solo, con trabajo diario para clientes y muchas PoCs propias pendientes. Busca un pequeño "equipo de desarrollo" de agentes de IA, autoalojado, que programe, pruebe, revise y documente de forma autónoma, incluso de noche. Eduardo debe poder intervenir en cualquier etapa: requerimientos, arquitectura o avance.

Principios acordados:

- GitHub es la fuente de verdad de cada proyecto (código, issues, PRs, discussions, CI/CD) y además la base de conocimiento de los agentes.
- Todo corre en Docker: primero en la Mac de Eduardo y después en la mini-PC 24/7.
- Se usan suscripciones (Claude Pro y ChatGPT), no APIs pagadas por uso. Como respaldo hay cuentas de API de Anthropic con un tope de USD 100.
- Se parte de un framework open source existente, no de cero.

### Descomposición del proyecto completo

| Fase | Alcance | Estado |
|---|---|---|
| **1. Piloto local** | OpenHands en Docker en la Mac, roles dev y reviewer, proyecto `qr-generator` | **Este documento** |
| 2. Roles y flujo de equipo | Más roles (tester, docs, arquitecto), paralelismo, GitHub como base de conocimiento | Futuro |
| 3. Métricas y costos | Medición continua, presupuestos, tablero | Futuro |
| 4. Migración a la mini-PC | Beelink SEi12 (i5-1235U, 32 GB) con Proxmox, VM Ubuntu + Docker; se sugieren unos 16 GB y 8 vCPU | Futuro |

### Criterios de éxito del piloto

- **A. Entrega autónoma:** un issue bien escrito termina en un PR mergeable con los tests pasando, sin que Eduardo escriba código. Él solo revisa y comenta.
- **C. Consumo sostenible:** con Claude Pro y ChatGPT se logra completar el MVP sin topar los límites de forma constante. Se mide cuántas tareas rinde cada ventana de 5 horas y cada semana.
- **E. Entregables visibles:** cada etapa del proyecto termina en un artefacto que se puede ver, probar o usar sin leer código. Su tipo depende de la etapa: un documento (por ejemplo, requerimientos), la app corriendo en un contenedor Docker, o un manual con scripts listos para instalar en la mini-PC. No hay una lista fija: en el piloto basta con que los agentes entreguen alguno y que sea útil tal cual.

No hay plazo fijo: se busca un resultado rápido sobre si la idea es viable.

## 2. Decisiones tomadas

| Decisión | Elección | Motivo / alternativa descartada |
|---|---|---|
| Framework | **OpenHands Agent Canvas**, self-hosted | El más maduro y pensado para Docker (≈90k⭐, MIT). Descartados: MetaGPT y ChatDev (solo API keys, poco mantenidos), CrewAI y LangGraph (habría que construir todo), Paperclip (integración con GitHub sin verificar). |
| Acceso a modelos | **Opción C:** Claude y Codex vía ACP usando las suscripciones | **Riesgo aceptado conscientemente:** `claude-agent-acp` está construido sobre el Claude Agent SDK, y los términos de Anthropic exigen API key en ese caso. Para mitigarlo se usa una **cuenta Claude Pro aparte**, nunca la cuenta Max de trabajo con clientes, y el uso será moderado. Plan B: el "modo híbrido", con Codex en OpenHands y Claude vía `claude-code-action` (el CLI oficial). |
| Conexión con GitHub | **Enfoque 2:** un **dispatcher** propio mínimo que consulta GitHub periódicamente y crea conversaciones por la API REST de Canvas | El enfoque 1 (automatizaciones nativas) quedó descartado: en la versión self-hosted de Canvas los disparadores por eventos de GitHub son solo de OpenHands Cloud (necesitan su GitHub App y un webhook), y lo único disponible es cron ([docs](https://docs.openhands.dev/automations/event-automations)). Un cron que despierte a un agente para revisar issues gastaría cuota sin hacer nada. El enfoque 3 (resolver vía Actions) se descartó porque usa API keys. |
| Organización en GitHub | `maxiar-org` | Separada del trabajo con clientes. |
| Identidad de los agentes | Cuenta bot **`maxiar-ai-dev-team-bot`** | Distingue el trabajo de los agentes, y solo Eduardo aprueba y mergea. |
| Roles del piloto | **Dev** (con TDD, cubre también el testing) y **Reviewer** | Mínimo viable; el resto de los roles es para la fase 2. |
| Proyecto piloto | `qr-generator`, en Flutter | Una sola base de código: web instalable primero y app de iOS con impresión directa después. |

## 3. Arquitectura y componentes

### Repositorios (en `maxiar-org`)

- **`ai-dev-team`** (esta carpeta, `~/ai-dev-team`): la infraestructura del equipo.
  - `docker-compose.yml`, `.env.example` (el `.env` real no se versiona)
  - `roles/dev.md`, `roles/reviewer.md`: instrucciones de cada rol
  - `github/labels.yml`, `github/ISSUE_TEMPLATE/agent-task.md`: se sincronizan a cada proyecto
  - `canvas/Dockerfile`: imagen de Canvas con Flutter y `gh` preinstalados
  - `dispatcher/`: servicio Python que conecta GitHub con Canvas (con tests)
  - `pilot/metrics.csv` (generado por el dispatcher), `pilot/REPORT.md`
  - `docs/`: specs, planes y bitácora
- **`qr-generator`:** proyecto piloto en Flutter, con `AGENTS.md` (convenciones), CI en GitHub Actions y backlog en issues.

### Servicios Docker (Mac, después mini-PC)

```
docker compose (ai-dev-team)
├─ canvas        → imagen propia FROM ghcr.io/openhands/agent-canvas:1.24.0
│                  + Flutter SDK + gh. Todo en un contenedor: UI, Agent Server,
│                  y los agentes ACP corriendo como subprocesos:
│                  ├─ claude-agent-acp  (cuenta Claude Pro del piloto)
│                  └─ codex-acp         (cuenta ChatGPT)
│                  UI en http://localhost:8000/canvas
├─ dispatcher    → Python; cada 60 s consulta GitHub (sin gastar cuota de
│                  modelos) y crea/monitorea conversaciones vía la API de Canvas
└─ volúmenes     → canvas-state (~/.openhands), projects (/projects, compartido
                   entre canvas y dispatcher), dispatcher-state (estado + métricas)
```

**Sin sandbox por tarea:** la imagen de Canvas ejecuta los agentes dentro del mismo contenedor ([arquitectura](https://docs.openhands.dev/openhands/usage/agent-canvas/architecture)). Cada tarea trabaja en su propia copia del repo en `/projects/<repo>/<tarea>`, que prepara el dispatcher. Dos conversaciones con el mismo motor comparten `HOME` y pueden pisarse los archivos de login, por eso el límite es **1 tarea por motor a la vez**.

### Dispatcher

Es un servicio sin estado propio importante: el estado de cada tarea vive en los labels de GitHub, y un archivo JSON (`dispatcher-state/state.json`) guarda solo lo efímero: conversaciones activas, comentarios ya procesados y rondas de review.

En cada ciclo:
1. Lee de GitHub los issues y PRs abiertos de los repos configurados.
2. Lee de Canvas el estado de las conversaciones activas (`GET /api/conversations?ids=…`).
3. Una función pura decide las acciones (iniciar tarea, cerrar tarea, marcar `needs:human`, pedir review) a partir de esas dos entradas.
4. Ejecuta las acciones: prepara la copia del repo, crea la conversación (`POST /api/conversations` con `agent_settings` del motor, `workspace.working_dir` y el prompt del rol), actualiza labels y comentarios, y registra métricas.

**Seguridad:** solo reacciona a comentarios `@openhands` de los usuarios en `ALLOWED_USERS` (Eduardo). Los labels que inician tareas solo los puede poner alguien con permiso de escritura en el repo.

### Credenciales y seguridad

- **No se monta el `~/.claude` ni el `~/.codex` del host.** Las credenciales se generan en contenedores descartables y se cargan como variables en `.env`:
  - `CLAUDE_CODE_OAUTH_TOKEN`: lo genera `claude setup-token` iniciando sesión con la **cuenta Pro del piloto** (dura 1 año).
  - `CODEX_AUTH_JSON`: el contenido de `~/.codex/auth.json` después de `codex login --device-auth` con la cuenta de ChatGPT.
- `LOCAL_BACKEND_API_KEY` protege la API de Canvas; el dispatcher la usa en el header `X-Session-API-Key`.
- `maxiar-ai-dev-team-bot` usa un token con permisos acotados solo a `maxiar-org` (contents, issues y pull requests en lectura y escritura). El token va en `.env`, que está en `.gitignore`.
- Respaldo: la API key de Anthropic (tope USD 100) queda comentada en `.env`. No se deben definir las dos a la vez: activarla es un cambio consciente de Eduardo.
- En `qr-generator`, `main` queda protegida: exige PR, que pase el CI y una aprobación de Eduardo. El bot no puede saltarse esa protección.

### Portabilidad

Se usan imágenes multiplataforma (arm64 en la Mac, amd64 en la mini-PC) y nada que dependa de macOS. Migrar consiste en clonar `ai-dev-team`, copiar `.env` y ejecutar `docker compose up --build`.

## 4. Flujo de trabajo

### Motores por defecto

| Rol | Motor por defecto | Motivo |
|---|---|---|
| Dev | Codex (`engine:codex`) | Implementar consume más, y ChatGPT tiene más margen que Claude Pro. |
| Reviewer | Claude (`engine:claude`) | Revisar consume menos, y un reviewer de otro modelo detecta más problemas. |

Los motores se invierten por tarea cambiando el label `engine:*` del issue.

### Ciclo de vida de un issue

```
Eduardo: issue con plantilla (contexto, criterios de aceptación, entregable visible, fuera de alcance)
 │  label agent:dev
 ▼
DEV (copia propia del repo): lee AGENTS.md + roles/dev.md → rama agent/<n>-<slug>
 │  TDD: test → código → flutter analyze + flutter test
 │  ¿dudas? → comenta preguntas en el issue + label needs:human → se detiene
 ▼
PR "Closes #n"; el dispatcher le pone agent:review   (CI corre en paralelo)
 ▼
REVIEWER (otro motor): review como comentario en el PR, que termina con
 │  VEREDICTO: APROBADO o VEREDICTO: CAMBIOS
 │  (el bot no puede aprobar ni rechazar formalmente su propio PR)
 │  ¿CAMBIOS? → el dispatcher lanza al DEV de nuevo sobre la rama del PR
 │  máximo 2 rondas automáticas → después needs:human
 ▼
APROBADO → el dispatcher te pide review en GitHub
 ▼
Eduardo: revisa, comenta (@openhands para pedir cambios) o aprueba y mergea
```

### Entregable visible por issue

La plantilla `agent-task.md` incluye el campo **Entregable visible**: qué podrá ver, probar o usar Eduardo al terminar (documento, app en contenedor, script, manual). El dev lo incluye en el PR, con instrucciones para verlo, y el reviewer verifica que esté presente y que funcione.

### Puntos de intervención de Eduardo

1. Escribir o refinar el issue antes de ponerle el label.
2. Responder los `needs:human`.
3. Comentar en cualquier PR con `@openhands`.
4. Aprobar y mergear: el agente **nunca** mergea.
5. Ver el avance en vivo en la UI de Canvas.

### Límites del piloto

- Máximo **1 tarea por motor** a la vez (o sea, hasta 2 en paralelo: una Codex y una Claude).
- Máximo **2 rondas** automáticas entre reviewer y dev.
- **60 minutos** de conversación → el dispatcher la pausa (`POST /api/conversations/{id}/pause`) y marca `needs:human`.

### Labels

`agent:dev`, `agent:working` (lo pone el dispatcher mientras hay una conversación activa), `agent:review`, `needs:human`, `engine:claude`, `engine:codex`. Se definen en `ai-dev-team/github/labels.yml` y se sincronizan con `gh label` a cada proyecto.

## 5. Métricas y manejo de errores

### Métricas (`pilot/metrics.csv`)

El dispatcher escribe una fila cada vez que termina una conversación:

| Campo | Fuente |
|---|---|
| `repo`, `numero`, `tipo` (issue/pr), `rol`, `motor` | La tarea que lanzó el dispatcher |
| `inicio`, `fin`, `duracion_min` | Reloj del dispatcher |
| `estado_final` | Estado de Canvas: `finished`, `error`, `stuck` o `timeout` |
| `resultado` | `pr_abierto`, `needs_human`, `aprobado`, `cambios` o `sin_resultado` |
| `tokens_entrada`, `tokens_salida`, `tokens_cache`, `costo_estimado_usd` | `stats` de la conversación en Canvas, que reporta los tokens también para los agentes ACP. El costo es una estimación a precios de API: sirve para comparar, no es lo que se paga con la suscripción. |

Si se mergeó o no cada PR se consulta al momento del reporte final, con `python -m dispatcher report`, que combina el CSV con el estado actual en GitHub.

### Reporte final (`pilot/REPORT.md`)

- **Criterio A:** porcentaje de issues que terminaron en PR mergeado sin código de Eduardo; rondas promedio; motivos de `needs:human`.
- **Criterio C:** tareas por ventana de 5 horas y por semana para cada motor; si fue necesario recurrir a la API, cuánto se gastó.
- **Criterio E:** qué entregables visibles produjeron los agentes, con enlace a cada uno, y cuánto tuvo que corregirlos Eduardo antes de que fueran útiles.
- Recomendación: seguir con la fase 2, pasar al modo híbrido o descartar la idea.

### Manejo de errores

| Situación | Respuesta |
|---|---|
| Se agotan los límites de un motor | El agente falla, se pone `needs:human` y un comentario con el motivo. Eduardo puede reintentar con el otro motor (cambiando el label) o activar la API de respaldo. |
| El CI falla en un PR | El reviewer lo marca y el dev itera (cuenta como ronda). |
| El agente se cuelga o pasa los 60 minutos | `needs:human`; la conversación queda en Canvas para diagnóstico. |
| Expira el login de un CLI o se cae Canvas | La conversación termina en `error` y el dispatcher marca `needs:human` con un comentario que incluye el último mensaje del agente. Si Canvas no responde, el dispatcher lo registra en su log y reintenta en el siguiente ciclo sin tocar GitHub. |
| El agente intenta mergear o escribir en `main` | La protección de la rama lo bloquea. |

## 6. Validación y arranque

### Paso 0: verificación de la infraestructura (lista de comprobación)

1. `docker compose up` deja Canvas accesible en `localhost`.
2. Claude (Pro) y Codex (ChatGPT) responden vía ACP desde Canvas, con las credenciales de `.env`, y `flutter --version` y `gh auth status` funcionan dentro del contenedor.
3. El bot clona el repo, crea una rama y abre un PR en un repo de prueba de `maxiar-org`.
4. **Prueba de punta a punta:** en el repo de prueba, un issue simple con `agent:dev` termina en un PR revisado por el otro motor, con una fila en `metrics.csv` que incluye tokens.
5. La protección de `main` impide que el bot mergee.

### Proyecto piloto `qr-generator`

**Usuario:** Maxi, que recorre comercios en Argentina con plantillas ya impresas (portarretrato de mostrador, colgante de tarjetero, adhesivo para cajas) y una impresora térmica **Detonger DT01** (Bluetooth, 58 mm, 203 ppp, unos 464 px de ancho imprimible) que usa desde un **iPhone** con la app WePrint.

**Impresión:**
- **MVP:** la app genera una imagen lista para imprimir. Maxi la guarda en Fotos y la importa desde WePrint (WePrint no aparece en el menú "Compartir" de iOS). También existe la opción de copiar el link y armar el QR dentro de WePrint.
- **Más adelante:** impresión directa con el SDK **LPAPI de Dothantech** (fabricante de Detonger y WePrint). Existe un plugin de Flutter que muestra exactamente el modelo DT01.

**Backlog inicial** (∥ = puede trabajarse en paralelo):

1. **Scaffold:** app Flutter (web instalable + iOS), estructura, `AGENTS.md`, CI (analyze + test).
2. ∥ **QR de WhatsApp:** normaliza números argentinos a `wa.me/549…`, con mensaje inicial opcional.
3. ∥ **QR de Instagram:** acepta tanto el link como `@usuario`.
4. ∥ **Diseño de impresión:** imagen de 464 px de ancho (QR + ícono + texto) en variantes por plantilla. Las medidas las confirma Eduardo con Maxi.
5. **Guardar en Fotos y copiar link:** flujo hacia WePrint.
6. **Google Reseñas** (research + implementación): pasar de un link de Maps al link directo para dejar una reseña.
7. **Mercado Pago Argentina** (spike): comparar alias/CVU, link de pago y QR interoperable (Transferencias 3.0), y proponer una opción.
8. **Impresión directa** (spike): LPAPI con la DT01 en iOS desde Flutter.

Cada issue declara su **entregable visible** (ver la plantilla en la sección 4). Por ejemplo: el 1 puede entregar la app vacía corriendo en un contenedor, el 7 un documento comparativo, y el 5 la app con el flujo completo para probar en el iPhone.

**El piloto termina** cuando se mergean los issues 1 a 5 (MVP utilizable por Maxi) o cuando Eduardo lo decida. Al cierre se escribe `pilot/REPORT.md`.

## 7. Fuera de alcance (fase 1)

- Roles de tester, docs y arquitecto como agentes separados.
- Tableros, presupuestos automáticos y alertas de consumo.
- Despliegue en la mini-PC.
- Publicación de `qr-generator` en la App Store.
- Uso de la cuenta Claude Max de trabajo con clientes, bajo ninguna circunstancia.

## 8. Riesgos

| Riesgo | Mitigación |
|---|---|
| Anthropic bloquea el uso de la suscripción vía ACP | Cuenta Pro aparte; pasar al modo híbrido o a la API de respaldo. |
| La API de Canvas cambia entre versiones | Se fija la versión de la imagen (`1.24.0`) y el cliente del dispatcher se aísla en un solo módulo. |
| Los límites de Claude Pro son muy bajos para 2 tareas en paralelo | Dev con Codex por defecto; bajar a 1 tarea en paralelo; usar la API de respaldo. |
| Bug de autenticación headless de Codex vía ACP ([OpenHands SDK #5167](https://github.com/OpenHands/software-agent-sdk/issues/5167)) | Se verifica en el paso 0.2; alternativa: `codex login --device-auth` dentro del contenedor. |
| Al probar desde el iPhone por HTTP en la red local, el navegador no permite copiar al portapapeles ni instalar la web como app (exigen HTTPS) | Para la prueba en red local alcanza con "Guardar imagen". Si hace falta, se agrega HTTPS con un certificado local o un túnel; si escala, pasa a la fase 4. |
| La imagen de Canvas con Flutter es pesada (varios GB) | Se construye una vez; la caché de `pub` vive en el volumen `projects`. |
| Todos los agentes comparten un contenedor (sin aislamiento entre tareas) | Aceptado para el piloto: los repos son propios y el token del bot solo alcanza a `maxiar-org`. Para la fase 2 se puede evaluar el runtime Docker por conversación. |

## 9. Fuentes

- OpenHands ACP: https://docs.openhands.dev/openhands/usage/agent-canvas/acp-agents
- Términos de Anthropic sobre suscripciones: https://code.claude.com/docs/en/legal-and-compliance
- Autenticación de Claude Code: https://code.claude.com/docs/en/authentication
- Autenticación de Codex: https://learn.chatgpt.com/docs/auth
- Plugin LPAPI para Flutter: https://pub.dev/packages/flutter_dothantech_lpapi_thermal_printer
