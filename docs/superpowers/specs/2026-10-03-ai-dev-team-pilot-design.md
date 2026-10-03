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

No hay plazo fijo: se busca un resultado rápido sobre si la idea es viable.

## 2. Decisiones tomadas

| Decisión | Elección | Motivo / alternativa descartada |
|---|---|---|
| Framework | **OpenHands Agent Canvas**, self-hosted | El más maduro y pensado para Docker (≈90k⭐, MIT). Descartados: MetaGPT y ChatDev (solo API keys, poco mantenidos), CrewAI y LangGraph (habría que construir todo), Paperclip (integración con GitHub sin verificar). |
| Acceso a modelos | **Opción C:** Claude y Codex vía ACP usando las suscripciones | **Riesgo aceptado conscientemente:** `claude-agent-acp` está construido sobre el Claude Agent SDK, y los términos de Anthropic exigen API key en ese caso. Para mitigarlo se usa una **cuenta Claude Pro aparte**, nunca la cuenta Max de trabajo con clientes, y el uso será moderado. Plan B: el "modo híbrido", con Codex en OpenHands y Claude vía `claude-code-action` (el CLI oficial). |
| Conexión con GitHub | **Enfoque 1:** automatizaciones nativas de Agent Canvas | Si no están disponibles en la versión open source, se pasa al **enfoque 2:** un despachador mínimo propio. El enfoque 3 (resolver vía Actions) se descartó porque usa API keys. |
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
  - `pilot/collect-metrics`, `pilot/healthcheck`, `pilot/metrics.csv`, `pilot/REPORT.md`
  - `docs/`: specs, planes y bitácora
- **`qr-generator`:** proyecto piloto en Flutter, con `AGENTS.md` (convenciones), CI en GitHub Actions y backlog en issues.

### Servicios Docker (Mac, después mini-PC)

```
docker compose (ai-dev-team)
├─ agent-canvas    → UI web + Agent Server (ghcr.io/openhands/agent-canvas)
│                    lanza agentes vía ACP:
│                    ├─ claude-agent-acp  (cuenta Claude Pro del piloto)
│                    └─ codex-acp         (cuenta ChatGPT)
├─ sandboxes       → un contenedor por tarea, creado por OpenHands
│                    (Flutter SDK + git + gh), con el repo clonado
└─ volúmenes       → credenciales de los CLIs y estado de Canvas
```

### Credenciales y seguridad

- **No se monta el `~/.claude` ni el `~/.codex` del host.** Los logins de Claude Pro y ChatGPT se hacen una vez *dentro* del contenedor y se guardan en volúmenes dedicados (`claude-auth`, `codex-auth`).
- `maxiar-ai-dev-team-bot` usa un token con permisos acotados solo a `maxiar-org` (contents, issues y pull requests en lectura y escritura). El token va en `.env`, que está en `.gitignore`.
- Respaldo: la API key de Anthropic (tope USD 100) se carga como secreto en Canvas, pero **inactiva** mientras el CLI tenga login. Solo se usa si Eduardo cambia a ese modo a propósito.
- En `qr-generator`, `main` queda protegida: exige PR, que pase el CI y una aprobación de Eduardo. El bot no puede saltarse esa protección.

### Portabilidad

Se usan imágenes multiplataforma (arm64 en la Mac, amd64 en la mini-PC) y nada que dependa de macOS. Migrar consiste en clonar `ai-dev-team`, restaurar los volúmenes (o volver a iniciar sesión) y ejecutar `docker compose up`.

## 4. Flujo de trabajo

### Motores por defecto

| Rol | Motor por defecto | Motivo |
|---|---|---|
| Dev | Codex (`engine:codex`) | Implementar consume más, y ChatGPT tiene más margen que Claude Pro. |
| Reviewer | Claude (`engine:claude`) | Revisar consume menos, y un reviewer de otro modelo detecta más problemas. |

Los motores se invierten por tarea cambiando el label `engine:*` del issue.

### Ciclo de vida de un issue

```
Eduardo: issue con plantilla (contexto, criterios de aceptación, fuera de alcance)
 │  label agent:dev
 ▼
DEV (sandbox): lee AGENTS.md + roles/dev.md → rama agent/<n>-<slug>
 │  TDD: test → código → flutter analyze + flutter test
 │  ¿dudas? → comenta preguntas en el issue + label needs:human → se detiene
 ▼
PR "Closes #n" + label agent:review         (CI corre en paralelo)
 ▼
REVIEWER (otro motor): review con comentarios en el PR
 │  ¿cambios? → @openhands en el PR → DEV itera
 │  máximo 2 rondas automáticas → después needs:human
 ▼
Eduardo: revisa, comenta (@openhands para pedir cambios) o aprueba y mergea
```

### Puntos de intervención de Eduardo

1. Escribir o refinar el issue antes de ponerle el label.
2. Responder los `needs:human`.
3. Comentar en cualquier PR con `@openhands`.
4. Aprobar y mergear: el agente **nunca** mergea.
5. Ver el avance en vivo en la UI de Canvas.

### Límites del piloto

- Máximo **2 tareas en paralelo**.
- Máximo **2 rondas** automáticas entre reviewer y dev.
- **60 minutos** sin abrir un PR → `needs:human`.

### Labels

`agent:dev`, `agent:review`, `needs:human`, `engine:claude`, `engine:codex`. Se definen en `ai-dev-team/github/labels.yml` y se sincronizan con `gh label` a cada proyecto.

## 5. Métricas y manejo de errores

### Métricas (`pilot/metrics.csv`)

Una fila por tarea y rol:

| Campo | Fuente |
|---|---|
| `issue`, `pr`, `rol`, `motor` | Labels y referencias de GitHub |
| `inicio`, `pr_abierto`, `fin`, `duracion_min` | Historial de eventos de GitHub (label aplicado, PR abierto o mergeado) |
| `rondas_review`, `needs_human` | Comentarios y labels |
| `resultado` | `mergeado` / `rechazado` / `abandonado` |
| `tokens` / `cuota` | Logs de los CLIs en Canvas cuando estén disponibles; si no, anotación manual del consumo visto en claude.ai y en ChatGPT |

`pilot/collect-metrics` es un script que se ejecuta a demanda (no un servicio) y regenera el CSV a partir de la API de GitHub.

### Reporte final (`pilot/REPORT.md`)

- **Criterio A:** porcentaje de issues que terminaron en PR mergeado sin código de Eduardo; rondas promedio; motivos de `needs:human`.
- **Criterio C:** tareas por ventana de 5 horas y por semana para cada motor; si fue necesario recurrir a la API, cuánto se gastó.
- Recomendación: seguir con la fase 2, pasar al modo híbrido o descartar la idea.

### Manejo de errores

| Situación | Respuesta |
|---|---|
| Se agotan los límites de un motor | El agente falla, se pone `needs:human` y un comentario con el motivo. Eduardo puede reintentar con el otro motor (cambiando el label) o activar la API de respaldo. |
| El CI falla en un PR | El reviewer lo marca y el dev itera (cuenta como ronda). |
| El agente se cuelga o pasa los 60 minutos | `needs:human`; la conversación queda en Canvas para diagnóstico. |
| Expira el login de un CLI | `pilot/healthcheck` (diario) lo detecta y abre un issue en `ai-dev-team`. |
| El agente intenta mergear o escribir en `main` | La protección de la rama lo bloquea. |

## 6. Validación y arranque

### Paso 0: verificación de la infraestructura (lista de comprobación)

1. `docker compose up` deja Canvas accesible en `localhost`.
2. Claude (Pro) y Codex (ChatGPT) responden vía ACP desde Canvas, con los logins guardados en volúmenes.
3. El bot clona el repo, crea una rama y abre un PR en un repo de prueba de `maxiar-org`.
4. **Prueba decisiva:** el label `agent:dev` dispara la automatización en la versión open source. **Si no la dispara:** se detiene, se avisa a Eduardo y se diseña el enfoque 2 (despachador mínimo) antes de seguir.
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
| Las automatizaciones de GitHub de Canvas son solo Enterprise | Se detecta en el paso 0.4 y se pasa al enfoque 2. |
| Los límites de Claude Pro son muy bajos para 2 tareas en paralelo | Dev con Codex por defecto; bajar a 1 tarea en paralelo; usar la API de respaldo. |
| Bug de autenticación headless de Codex vía ACP ([OpenHands SDK #5167](https://github.com/OpenHands/software-agent-sdk/issues/5167)) | Se verifica en el paso 0.2; alternativa: `codex login --device-auth` dentro del contenedor. |
| La imagen de Flutter en los sandboxes es pesada o lenta | Imagen de sandbox propia con Flutter preinstalado y caché de `pub`. |

## 9. Fuentes

- OpenHands ACP: https://docs.openhands.dev/openhands/usage/agent-canvas/acp-agents
- Términos de Anthropic sobre suscripciones: https://code.claude.com/docs/en/legal-and-compliance
- Autenticación de Claude Code: https://code.claude.com/docs/en/authentication
- Autenticación de Codex: https://learn.chatgpt.com/docs/auth
- Plugin LPAPI para Flutter: https://pub.dev/packages/flutter_dothantech_lpapi_thermal_printer
