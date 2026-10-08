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
   - `operador/` → **`operador` (tú mismo): no lo incluyas en el paso 5.** Usa el procedimiento del final.
   - `docker-compose.yml` → los servicios que tocó.
5. Ejecuta `docker compose up -d --build <servicios>`, nombrando siempre los servicios explícitamente y **sin `operador`**.
6. Verifica:
   - `docker compose ps` muestra todo en `running`;
   - `docker compose logs --since 2m <servicio>` no tiene errores;
   - el latido es reciente (`docker compose exec dispatcher cat /state/heartbeat`).
7. Reporta qué se desplegó y el resultado.

## Actualizarte a ti mismo (servicio `operador`)

Si `docker compose` corre dentro de tu contenedor, muere cuando Compose lo reemplaza. Delega en un contenedor descartable que sigue vivo después de que el tuyo se detiene:

```bash
docker run --rm -d --name operador-redeploy \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /opt/ai-dev-team:/opt/ai-dev-team -w /opt/ai-dev-team \
  docker:cli compose up -d --build operador
```

Antes, avisa a Eduardo que la sesión se va a cortar 1 o 2 minutos y que tiene que volver a abrir la sesión "operador" en la app.
