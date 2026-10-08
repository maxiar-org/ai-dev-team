# Fase 4d: vista de estado (diseño)

- **Fecha:** 2026-10-08
- **Autor:** Eduardo Jiménez (con Claude)
- **Estado:** aprobado en conversación, pendiente de revisión escrita
- **Antecedentes:** fases 4a y 4b cerradas. 4c se posterga a la fase futura de mejoras (`docs/bitacora.md`).

## 1. Objetivo

Un **único lugar**, `https://estado.maxiar.dev`, que reemplace mirar el Kanban, preguntarle al operador y revisar Coolify. Al abrirlo desde el celular, en unos 5 segundos Eduardo sabe **qué le toca hacer y en qué orden**.

### Criterios de éxito

1. `estado.maxiar.dev` abre desde el celular detrás de Access y muestra cuatro secciones: **Qué espera de ti** (arriba), **Trabajo en curso**, **Despliegues** y **Salud y consumo**.
2. Con un PR aprobado por el agente que espera a Eduardo y un item con `needs:human`, los dos aparecen arriba, con links directos y el orden de merge sugerido.
3. La página se actualiza sola, con datos de hace menos de 2 minutos ("actualizado hace X s").
4. Si una fuente cae (por ejemplo, Coolify), su sección muestra "sin datos" y el resto funciona.
5. **Cero tokens de LLM:** todo se genera con reglas.

## 2. Decisiones

| Tema | Decisión |
|---|---|
| Generación | **Reglas fijas** (opción A). El botón "Resumen del operador" a pedido (opción C) queda reservado para más adelante: un recuadro vacío, previsto en la página |
| Dónde corre | Servicio **`estado`** en el `docker-compose.yml` de ai-dev-team, con la **misma imagen del dispatcher** (`python -m dispatcher.estado`). Todo en Docker |
| Acceso | `estado.maxiar.dev` por el túnel `ai-dev-team`, detrás de **Access** (email de Eduardo). Solo lectura |
| Interfaz | HTML generado en el servidor, pensado para el celular, en modo oscuro, que se recarga sola cada 60 s. Sin frameworks ni JavaScript de aplicación |

## 3. Contenido

### 3.1 Qué espera de ti (siempre arriba)
- **PRs para revisar o mergear:**
  - **Condición:** PR abierto, con pedido de review a Eduardo o sin labels de agente activos (ni `agent:*` ni `needs:human`), cuya última acción del agente fue de cierre (QA OK, QA N/A o review sobre fix).
  - **Cada PR muestra:** título, repo, issue vinculado, link al PR, link a la preview (`<p>-pr-N.maxiar.dev`) si existe, estado del CI y conflictos.
  - **Orden de merge sugerido:**
    1. los que no tienen conflictos y tienen CI en verde, antes que los demás;
    2. si el issue de un PR depende de otro (`Depende de #N`), primero el de #N;
    3. el resto, por número de PR (el más viejo primero).

    Si dos PRs listos tocan los mismos archivos, se avisa: "puede generar conflicto con #M".
- **`needs:human`:** el item, su link y un extracto del último comentario del bot.
- **Alertas `[ops]` abiertas**, y **tokens por vencer en 30 días o menos** (a partir de `GITHUB_TOKEN_EXPIRES` y `CLAUDE_TOKEN_EXPIRES`).
- Si no hay nada: "Nada pendiente 🎉".

### 3.2 Trabajo en curso (por proyecto)
- Cada issue o PR abierto con su **etapa**, derivada de los labels y del estado del dispatcher: `dev`, `review`, `QA`, `fix`, `docs`, `bloqueado (depende de #N)`, `listo para agentes` o `backlog`. También el **motor** y **hace cuánto empezó** si hay una tarea activa.

### 3.3 Despliegues
- Por cada app de Coolify: nombre, URL estable, estado y fecha del último despliegue.
- **Previews activas** con su link y el PR al que corresponden.

### 3.4 Salud y consumo
- Los mismos chequeos del watchdog (Canvas, latido del dispatcher, túnel, Coolify y disco), calculados en el momento.
- Tareas en las últimas 24 horas y en los últimos 7 días **por motor**, con sus minutos, a partir de `pilot/metrics.csv`.

### 3.5 Resumen del operador (reservado)
- Un recuadro con el texto "Próximamente: resumen narrativo a pedido". Se implementa después (opción C).

## 4. Arquitectura

```
estado (python -m dispatcher.estado)
 ├─ recolector (cada 60 s, en un hilo): GitHub API, /state/state.json (ro),
 │    /pilot/metrics.csv (ro), Canvas API, Coolify API, run_checks del watchdog
 ├─ build_view(datos) → modelo de la vista   ← función pura, con tests
 ├─ render(modelo) → HTML                     ← función pura, con tests
 └─ servidor HTTP (librería estándar) en :8090: GET / devuelve el último HTML; GET /health
```

- Reutiliza `GitHubClient`, `CanvasClient`, `run_checks` y `parse_dependencies`, más un `CoolifyClient` mínimo nuevo (aplicaciones, despliegues y previews).
- Si una fuente falla, el error se guarda por sección: la sección muestra "sin datos (motivo)" y el resto sigue funcionando.
- Variables: las que ya usan el dispatcher y el watchdog, más `COOLIFY_API_URL` (`http://coolify:8080/api/v1`) y `COOLIFY_API_TOKEN`.

## 5. Fuera de alcance

- Acciones desde la vista (mergear, etiquetar): para eso están los links a GitHub.
- Botón del operador (C), historial y gráficos (Grafana): más adelante.
- 4c (eventos de GitHub).

## 6. Riesgos

| Riesgo | Mitigación |
|---|---|
| Límite de la API de GitHub (5000 por hora por token) | Una recolección cada 60 s, con unas 10 a 20 llamadas por ciclo (unas 1200 por hora). Comparte token con el dispatcher (unas 600 por hora). Hay margen |
| La regla de "listo para Eduardo" no coincide con la realidad | Con tests sobre casos reales del piloto; se ajusta con el uso |
| La vista queda expuesta | Access, igual que Canvas y Coolify |
