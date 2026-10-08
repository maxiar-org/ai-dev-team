---
name: desplegar
description: Desplegar cambios del repo ai-dev-team en la mini-PC con verificación (pull, tests, rebuild de los servicios afectados, chequeo). Usar cuando Eduardo pide "desplegá", "actualizá el dispatcher" o algo similar.
---

# Desplegar ai-dev-team

1. Ejecuta `git -C /opt/ai-dev-team pull` y anota qué cambió: `git log --oneline HEAD@{1}..HEAD`.
2. Si cambió `dispatcher/`, ejecuta `cd dispatcher && uv run pytest -q`. **Si falla, detente** y reporta.
3. Ejecuta `docker compose exec dispatcher cat /state/state.json`. Si `active` no está vacío, avisa qué tareas se interrumpirían y pide confirmación.
4. Decide qué servicios se afectaron:
   - `dispatcher/` → `dispatcher` y `watchdog`;
   - `canvas/` → `canvas`;
   - `roles/` → `dispatcher`, porque lee las plantillas en cada tarea, así que alcanza con el pull, sin rebuild;
   - `operador/` → `operador` (avisa que tu sesión se va a reiniciar);
   - `docker-compose.yml` → los servicios que tocó.
5. Ejecuta `docker compose up -d --build <servicios>`.
6. Verifica:
   - `docker compose ps` muestra todo en `running`;
   - `docker compose logs --since 2m <servicio>` no tiene errores;
   - el latido es reciente (`docker compose exec dispatcher cat /state/heartbeat`).
7. Reporta qué se desplegó y el resultado.
