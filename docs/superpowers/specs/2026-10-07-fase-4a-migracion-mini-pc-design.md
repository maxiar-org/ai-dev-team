# Fase 4a: migración a la mini-PC, autonomía y operador remoto (diseño)

- **Fecha:** 2026-10-07
- **Autor:** Eduardo Jiménez (con Claude)
- **Estado:** aprobado en conversación, pendiente de revisión escrita
- **Contexto:** la fase 4 se divide en 4a (este documento), 4b (Coolify y previews), 4c (eventos de GitHub) y 4d (vista de estado). Ver `docs/bitacora.md`.

## 1. Objetivo

Que el AI Dev Team funcione al 100 % en la mini-PC, **sin depender de la Mac**, y que Eduardo pueda operarlo desde cualquier lugar: el celular, claude.ai o GitHub.

### Principio: todo en Docker Compose

**En el host solo hay Docker** (Engine y el plugin Compose). Todo lo demás es un servicio del `docker-compose.yml`: Canvas, dispatcher, túnel, watchdog y operador. Mudar la infraestructura a otra máquina es instalar Docker, copiar el repo, el `.env` y los volúmenes, y ejecutar `docker compose up -d`.

### Criterios de éxito (entregable visible)

1. **Con la Mac apagada:** un issue de prueba en `agent-playground` con `agent:dev` recorre dev → review → QA → pedido de review.
2. `https://canvas.maxiar.dev` se abre desde el celular después de un login con Cloudflare Access, y muestra las conversaciones.
3. Eduardo le pregunta "¿status?" al **operador** (Claude Code en la mini-PC) desde la app de Claude y recibe el resumen de hecho, pendiente y acciones sugeridas.
4. Si el dispatcher se detiene a propósito, aparece un issue `ops` en `ai-dev-team` en menos de 10 minutos, y se cierra solo cuando se recupera.
5. La mini-PC sobrevive a un reinicio: todo vuelve a levantarse solo (stack, túnel, watchdog y operador).

## 2. Situación de partida

| | Mac (hoy) | Mini-PC (`ssh ubuntu-labs`) |
|---|---|---|
| Stack | Canvas y dispatcher en Docker Desktop | Nada; **Docker no está instalado** |
| Recursos | — | Ubuntu 26.04 LTS, x86_64, **8 vCPU, 15 GB de RAM**, 116 GB de disco (104 GB libres), IP `192.168.1.101` |
| Otros | Túnel temporal `trycloudflare` para la app de qr-generator | **`hermes`** (agente de Eduardo) en `192.168.1.101:9119`: **no se toca** |
| Usuario | `eduardo` | Hoy se entra como `root` |

## 3. Diseño

### 3.1 Base

- Docker Engine y el plugin Compose desde el repositorio oficial de Docker, con el servicio habilitado al arranque.
- **Usuario dedicado `aidev`**, en el grupo `docker` y sin login por contraseña (se entra desde `root` con `sudo -iu aidev`). Es dueño de `/opt/ai-dev-team` y ejecuta `docker compose`. No tiene servicios propios en el host.
- El repo `maxiar-org/ai-dev-team` se clona en `/opt/ai-dev-team` (dueño `aidev`). Para hacer push con la sesión de `gh` de `aidev` se usa el helper de credenciales local del repo, igual que en la Mac.
- El `.env` se copia desde la Mac con `scp`, con permisos `600`. Nunca pasa por GitHub.

### 3.2 Migración del estado (corte)

1. Esperar a que el dispatcher de la Mac **no tenga tareas activas** y detenerlo (`docker compose stop dispatcher`).
2. Exportar los volúmenes `canvas-state`, `codex-home` y `dispatcher-state` a archivos tar (con un contenedor `alpine` temporal), copiarlos a la mini-PC e importarlos. `projects` no se migra: el dispatcher vuelve a clonar.
3. En la mini-PC, `docker compose build` (las imágenes se recompilan para x86_64) y `docker compose up -d`.
4. Verificar: Canvas responde, ACP Claude y Codex responden, el MCP de Playwright funciona, y el dispatcher hace ciclos sin errores.
5. Hacer la prueba de punta a punta con un issue en `agent-playground`.
6. En la Mac: `docker compose down` y apagar `qr-app` y `qr-tunnel` (la URL temporal deja de existir; en la 4b la reemplaza `qr.maxiar.dev`).

### 3.3 Dominio y acceso

- Eduardo compra **`maxiar.dev`** en Cloudflare Registrar.
- **Cloudflare Tunnel con nombre** (`ai-dev-team`). Corre como servicio `cloudflared` dentro del `docker-compose.yml`, con `TUNNEL_TOKEN` en `.env`. No se abre ningún puerto en el router.
- La ruta pública `canvas.maxiar.dev` apunta a `http://canvas:8000`.
- **Cloudflare Access**: una aplicación para `canvas.maxiar.dev`, con política "email de Eduardo" (código por email).
- El puerto `127.0.0.1:8000` sigue disponible dentro de la mini-PC, para diagnóstico.
- Los subdominios `coolify`, `qr`, `pr-*`, `hooks` y `estado` se agregan en 4b, 4c y 4d.

### 3.4 Operación sin supervisión

- **Latido:** al final de cada ciclo, el dispatcher escribe la hora en `/state/heartbeat`.
- **Watchdog**: servicio `watchdog` del compose (`ops/watchdog.py`, en un ciclo cada 5 minutos, `restart: unless-stopped`). **No monta el socket de Docker.**
  - **Chequeos:**
    - Canvas: `GET http://canvas:8000/api/conversations/count` con la clave responde 200;
    - dispatcher: el latido en el volumen `dispatcher-state` (montado en solo lectura) tiene menos de 5 minutos;
    - túnel: `GET http://cloudflared:2000/ready` (métricas de `cloudflared`, que se exponen solo en la red interna) responde 200;
    - disco: el uso del sistema de archivos que ve el contenedor (el disco de la VM) es menor al 85 %.

    Si un contenedor se cae, su chequeo falla.
  - **Si falla un chequeo** y no hay un issue `ops` abierto para ese chequeo, abre uno en `ai-dev-team` con el título `[ops] <chequeo>` y el detalle. Si se recupera, comenta en su issue y lo cierra.
  - **Vencimientos:** lee `GITHUB_TOKEN_EXPIRES` y `CLAUDE_TOKEN_EXPIRES` (fechas ISO en `.env`). 14 días antes de cada uno abre `[ops] Renovar <token> (vence <fecha>)`, una sola vez.
  - Usa la API REST de GitHub con el token del bot. La lógica pura (qué abrir o cerrar a partir de los resultados) va separada del I/O y tiene tests.
- **Reinicio:** `restart: unless-stopped` en todos los servicios y Docker habilitado al arranque. No hay timers ni servicios de `systemd` propios.
- **Backups:** **quedan para más adelante**, por decisión de Eduardo. Ver los riesgos.

### 3.5 Operador remoto

- Servicio **`operador`** del compose: una imagen propia (`operador/Dockerfile`) con Claude Code (CLI oficial), `git`, `gh`, `tmux`, `python3` y el cliente de Docker con el plugin Compose.
  - Su comando arranca `claude --remote-control` dentro de una sesión de `tmux` llamada `operador`, en `/opt/ai-dev-team`, y mantiene vivo el contenedor. Si `claude` termina, lo vuelve a lanzar.
  - **Volumen `operador-home`** para el `HOME` del contenedor (`~/.claude` con el login, la memoria y la configuración, más la configuración de `gh`). Sobrevive reinicios y se muda con el resto.
  - Monta el repo (`/opt/ai-dev-team`, lectura y escritura) y el **socket de Docker**, para poder desplegar y reiniciar el stack. ⚠️ Eso equivale a control total de Docker en la VM: es el único servicio con ese permiso y está documentado en `CLAUDE.md`.
  - Usa la **cuenta personal de Eduardo** (la misma que usa hoy en la Mac), **no** la cuenta Pro de los agentes. El login se hace una vez con `docker compose exec -it operador claude` (flujo de código pegado en el navegador).
  - Eduardo se conecta desde la app de Claude o desde claude.ai/code.
- **Conocimiento del operador:**
  - **`CLAUDE.md`** en la raíz de `ai-dev-team`:
    - arquitectura (Canvas como runtime, dispatcher como orquestador, GitHub como fuente de verdad);
    - comandos de operación y despliegue;
    - diagnóstico;
    - reglas: no tocar `hermes` ni los demás labs; nunca commitear `.env`; `main` solo por PR, salvo cambios del operador que Eduardo pida explícitamente.
  - **Skills** en `.claude/skills/` del repo:
    - `/estado`: el resumen de hecho, en curso, bloqueado, qué espera a Eduardo, en qué orden mergear, y el consumo;
    - `/desplegar`: pull, tests del dispatcher, `docker compose up -d --build` y verificación.
  - **Memoria:** se copia `~/.claude/projects/-Users-eduardo-ai-dev-team/memory/` de la Mac al volumen `operador-home`, en `~/.claude/projects/-opt-ai-dev-team/memory/`.
- **A verificar:** que la sesión aguante días y se reconecte. Si `claude` termina, el comando del contenedor lo relanza. Si Remote Control no se recupera solo, se suma un chequeo al watchdog.

## 4. Fuera de alcance

- Coolify, `qr.maxiar.dev` y las previews (4b); webhooks y eventos (4c); `estado.maxiar.dev` (4d).
- Backups de la VM en Proxmox (más adelante).
- GitHub Team (cuando haya un proyecto privado) y Google Cloud (producción y Places API).

## 5. Riesgos

| Riesgo | Mitigación |
|---|---|
| **Sin backups:** si la VM se rompe, se pierden los volúmenes (historial de Canvas, login de Codex, estado del dispatcher) | Todo se puede reconstruir desde el repo y el `.env` (que también se guarda en el gestor de contraseñas) más un login nuevo de Codex. Configurar `vzdump` en Proxmox apenas se pueda |
| Dos dispatchers procesando a la vez durante el corte | El de la Mac se detiene **antes** de levantar el de la mini-PC |
| El login de Codex en el volumen migrado se invalidó por una renovación en paralelo | Si falla, login nuevo por código (procedimiento del README) y se borra `codex-home` |
| Remote Control no aguanta días | El contenedor relanza `claude`. Si aun así falla, se usa con `docker compose exec -it operador tmux attach` y se reporta |
| El operador tiene el socket de Docker (control total de Docker en la VM) | Es su rol. Solo ese servicio lo tiene, y `CLAUDE.md` le prohíbe tocar contenedores, volúmenes o redes ajenos al proyecto `ai-dev-team` |
| `cloudflared` caído deja a Canvas inaccesible desde afuera (los agentes siguen funcionando) | Chequeo del watchdog sobre `cloudflared` |
| Conflictos con `hermes` u otros labs | Todo dentro del proyecto Compose `ai-dev-team`, sin puertos publicados en la IP de la LAN (todo por el túnel) y la regla explícita en `CLAUDE.md` |
