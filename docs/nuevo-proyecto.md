# Sumar un proyecto nuevo y forma de trabajo

Guía para incorporar un proyecto al AI Dev Team y para saber **dónde va cada conversación y cada cambio**. Surgió al sumar `nikito`, el segundo proyecto real después de `qr-generator`.

## Quién es quién

| Actor | Dónde corre | Para qué se usa | No se usa para |
|---|---|---|---|
| **Eduardo** | — | Decide, revisa y **es el único que mergea** | — |
| **Claude Code en la Mac** (esta conversación) | VS Code, abierto en `~/dev/maxiar-org/ai-dev-team` | Diseño de la plataforma; sumar proyectos (leer su documentación, escribir su `AGENTS.md`, armar issues); configurar Coolify, Access y la mini-PC; revisiones de fondo | Programar las funcionalidades de los proyectos: eso lo hacen los agentes |
| **Operador** (Remote Control "operador") | Contenedor en la mini-PC | Operar el día a día desde el celular: `/estado`, despliegues, reinicios, diagnóstico | Diseñar cosas nuevas o tocar el código de los proyectos |
| **Agentes** (OpenHands Canvas: Claude y Codex) | Canvas, en la mini-PC | Implementar los issues de cada proyecto: dev, review, QA, docs y fix | Cambiar la plataforma (`ai-dev-team` es de solo documentación para ellos) |

## Dónde va cada conversación

- **Siempre se abre en `ai-dev-team`,** aunque el tema sea un proyecto. La memoria de Claude Code es **por carpeta**: en `ai-dev-team` están el acceso a la mini-PC, Coolify, las convenciones y el estado de la plataforma. Abierta desde la carpeta del proyecto, arrancaría sin nada de eso.
- **La carpeta del proyecto se suma como directorio adicional:**
  - En la **extensión de VS Code** no existe `/add-dir`. Se usa `ai-dev-team/.claude/settings.local.json`, que es local y está ignorado por git:
    ```json
    {
      "permissions": {
        "additionalDirectories": [
          "/Users/eduardo/dev/maxiar-org/nikito"
        ]
      }
    }
    ```
    Se lee al **iniciar** la sesión: después de editarlo, abrir una conversación nueva.
  - En la **terminal** (`claude`): `/add-dir ../nikito` sirve solo para esa sesión.
- **Las instrucciones del proyecto no se cargan solas:** el `CLAUDE.md` o `AGENTS.md` de un directorio adicional **no se carga automáticamente**. Al empezar, pedile a Claude que los lea.
- **Una conversación por tema grande:** una por proyecto nuevo o por fase de la plataforma. Cuando una conversación se hace muy larga, se cierra con un **resumen de estado en la memoria** (lo pendiente y el próximo paso) y se abre otra.

## Dónde va cada cambio

| Cambio | Va en | Cómo |
|---|---|---|
| Código de la plataforma (dispatcher, Docker, operador) | `ai-dev-team` | PR de Claude Code con tests; mergea Eduardo |
| Documentación de la plataforma, convenciones y bitácora | `ai-dev-team` | PR (los agentes también pueden, con issues `agent:docs`) |
| Conocimiento del proyecto (stack, cómo verificar, flujos que no se rompen) | `AGENTS.md` del proyecto | PR, porque **es lo que leen los agentes** |
| Skills del proyecto | `.agents/skills/` del proyecto | PR de Claude Code (ver "Skills para los agentes" en el README) |
| Funcionalidades del proyecto | Repo del proyecto | Issue con `agent:dev`; lo implementan los agentes |
| Configuración de la mini-PC (`.env`, `REPOS`) | `/opt/ai-dev-team/.env` en la mini-PC | Claude Code o el operador, por SSH; nunca se commitea |
| Despliegues y secretos de apps | Coolify | Por su API o su panel; los secretos nunca van en un repo |

## Checklist para sumar un proyecto

### 1. Repositorio
- [ ] Crear el repo en `maxiar-org` y clonarlo en `~/dev/maxiar-org/<proyecto>`: `gh repo create maxiar-org/<proyecto> --private --add-readme`.
  - **Público:** `main` protegida (PR + 1 aprobación), igual que `qr-generator`.
  - **Privado:** con el plan gratuito de GitHub **no se puede proteger `main`**. "Solo Eduardo mergea" queda por convención hasta pasar a GitHub Team.
- [ ] Copiar los labels del flujo desde `qr-generator`:
  ```bash
  gh label list --repo maxiar-org/qr-generator --json name,color,description --limit 50 \
    --jq '.[]|select(.name|test("^(agent|engine|needs|post-piloto)"))|[.name,.color,.description]|@tsv' |
  while IFS=$'\t' read n c d; do gh label create "$n" --repo maxiar-org/<proyecto> --color "$c" --description "$d" --force; done
  ```
- [ ] **Darle escritura al bot.** No es automático: en un repo nuevo, el bot solo tiene lectura.
  ```bash
  gh api -X PUT repos/maxiar-org/<proyecto>/collaborators/maxiar-ai-dev-team-bot -f permission=push
  ```
  Para verificarlo, desde el contenedor del dispatcher el repo tiene que mostrar `push: True`.
- [ ] Si el `push` desde la Mac da 403, es porque el llavero entrega la cuenta de trabajo. Usar `gh repo clone` o forzar el helper de `gh`.

### 2. Plataforma (mini-PC)
- [ ] Sumar el repo a `REPOS` en `/opt/ai-dev-team/.env`.
- [ ] **Verificar que no haya tareas activas** (`state.json` → `active`).
- [ ] Recrear con `docker compose up -d --no-deps dispatcher estado`.
- [ ] Revisar en los logs del dispatcher que el repo nuevo se consulte con 200, y que aparezca en `estado.maxiar.dev`.

### 3. Conocimiento para los agentes
- [ ] Leer la documentación, la configuración y los mockups que subió Eduardo.
- [ ] Escribir o ajustar el `AGENTS.md` del proyecto:
  - stack;
  - **verificación obligatoria antes de un PR** (comandos exactos);
  - cómo probar la UI con Playwright;
  - flujos que nunca se rompen;
  - qué está prohibido;
  - convenciones (ramas `agent/<issue>-<slug>`, `Closes #N`, sección **Entregable visible**).
- [ ] Si el proyecto los necesita: skills en `.agents/skills/` con el enlace `.claude/skills`, y tareas de imágenes con `engine:codex` (ver el README).
- [ ] Revisar que el repo no tenga secretos ni archivos pesados que no correspondan (por ejemplo `.zip` o `.env`).

### 4. Despliegue (si es web)
- [ ] Crear la app en Coolify, en el proyecto `labs`, y activar las previews (ver "Coolify y previews" en el README).
  - Dominios: `<proyecto>.maxiar.dev` y `<proyecto>-pr-N.maxiar.dev`.
  - Si usa compose con base de datos, la app lee `SERVICE_NAME_<SVC>` en tiempo de ejecución.
- [ ] Crear una aplicación de Access para las previews (`<proyecto>-pr-*`), y otra para la versión estable si no es pública.
- [ ] Secretos solo como variables de entorno de Coolify, para producción y previews.

### 5. Primer lote de issues
- [ ] Issues chicos, cada uno con **criterios de aceptación**, **Entregable visible**, **Fuera de alcance** y **Depende de #N**.
- [ ] `engine:claude` o `engine:codex` cuando importe el motor (por ejemplo, diseño con skills o imágenes).
- [ ] Empezar con 1 o 2 issues con `agent:dev`, para ver cómo trabajan los agentes con el proyecto antes de cargar el resto.

### 6. Cierre
- [ ] Entrada en `docs/bitacora.md`, y actualizar esta guía con lo que haya faltado.
