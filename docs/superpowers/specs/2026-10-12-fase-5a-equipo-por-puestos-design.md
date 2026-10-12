# Fase 5a: equipo por puestos, asignación por tamaño y respaldo por límite de uso

- **Fecha:** 2026-10-12
- **Autor:** Eduardo Jiménez (con Claude)
- **Estado:** aprobado en conversación (partes 1 a 4), pendiente de revisión escrita
- **Spec hermano:** la fase 5b (pantalla de estado nueva) usa los datos que define este spec. Se diseña aparte.

## 1. Objetivo

Que el equipo avance más rápido con las cuentas disponibles y que se pueda medir cuánto cuesta un proyecto mediano en agentes y cuentas.

**Diagnóstico** (`pilot/metrics.csv`, primeras 23 h de nikito):
- **Uso real:** 39 tareas y solo unos 260 minutos de cómputo (Claude 161, Codex 98). Los agentes estuvieron parados la mayor parte del tiempo.
- **Cortes por límite de uso:** 4. Codex quedó fuera unas 7 horas, y como hacía el QA y la mayoría de las reviews, frenó todo.
- **Retrabajo:** más de la mitad del cómputo fue fix, review y QA repetidos. En nikito#21 fueron 11 tareas y 77 minutos.
- **Paralelismo:** hay una sola tarea por motor, así que el trabajo casi terminado esperaba mientras arrancaban tareas nuevas.

### Criterios de éxito

1. Si una cuenta llega a su límite, la tarea no queda con `needs:human`: pasa a otro puesto o espera el reinicio sola, y nunca arranca una tarea en un puesto agotado.
2. Tres puestos (Claude senior, Codex senior y Gemini) trabajan en paralelo, con QA en Gemini por defecto.
3. Las tareas se asignan solas según su tipo y su tamaño (`size:*`, `kind:architecture`, `needs:images`), y `engine:*` las sigue forzando.
4. Cada tarea, corte y consumo queda registrado **por puesto**, con los datos que necesita la fase 5b para mostrar consumo, límites y presupuesto.

## 2. Puestos

Un **puesto** es una cuenta de un motor, con un nivel. El dispatcher deja de razonar por motor y pasa a razonar por puesto: corre una tarea a la vez **por puesto**.

| Puesto | Motor | Cuenta | Nivel |
|---|---|---|---|
| `claude-senior` | `claude` | Max 5x (eduardo.jimenez@falconsoft.cl), compartida con el operador y con Claude Code | Senior y arquitecto |
| `codex-senior` | `codex` | Pro (servicios@falconsoft.cl) | Senior; imágenes gratis por la suscripción |
| `gemini` | `gemini` | Gemini Pro (suscripción) y API key paga | Dev de respaldo, QA e imágenes |

**Para más adelante, sin implementar ahora:** `claude-ssr` (Claude Pro de gmail) y `codex-ssr` (Codex Plus de gmail). Se suman solo si las métricas lo justifican (sección 7). El diseño ya los admite: un puesto más es una entrada más de configuración.

### 2.1 Configuración

La lista de puestos se define con una variable `SLOTS` en `/opt/ai-dev-team/.env`, por ejemplo `claude-senior:claude:senior,codex-senior:codex:senior,gemini:gemini:senior`. Cada puesto puede tener además un costo fijo mensual en USD (`SLOT_COST_<PUESTO>`) para el presupuesto.

Con un solo puesto por motor, las credenciales siguen como hoy:
- Claude, con el login en `~/.claude`;
- Codex, con `CODEX_AUTH_JSON` en `~/.codex`.

Para cambiar de cuenta se renuevan esas credenciales. **Cuando un motor tenga dos puestos,** cada uno usará su propio directorio de credenciales (`CLAUDE_CONFIG_DIR` y `CODEX_HOME`), con `acp_command` por conversación. Eso queda fuera del alcance de esta fase, salvo dejar el modelo de datos preparado.

### 2.2 Gemini como tercer motor

- **Cómo se conecta:** Gemini CLI en modo ACP dentro del contenedor de Canvas, igual que `claude-agent-acp` y `codex-acp`. Se loguea con la suscripción Pro y, si no se puede, usa la API key (`GEMINI_API_KEY`, que ya está en el `.env` para el MCP de imágenes).
- **Prueba previa obligatoria, antes de implementar el resto:**
  1. Instalar Gemini CLI en la imagen de Canvas, con versión fijada.
  2. Confirmar que Canvas lo acepta como `acp_server` (o con `acp_command`).
  3. Iniciar sesión con la suscripción y confirmar que el login persiste en un volumen.
  4. Correr una conversación de prueba que lea un repo y use los MCP `playwright` y `dart`.
- **Si la prueba falla,** el puesto `gemini` queda deshabilitado (fuera de `SLOTS`), el QA vuelve a `codex-senior` y el resto del spec sigue igual.

## 3. Etiquetas

Las etiquetas nuevas siguen la nomenclatura en inglés de las que ya existen:

| Etiqueta | Significado | Quién la pone |
|---|---|---|
| `size:S`, `size:M`, `size:L` | El tamaño de la tarea. Sin etiqueta, cuenta como `M`. Un `L` se parte en issues más chicos salvo que no se pueda | Claude Code al crear el issue |
| `kind:architecture` | Decisiones de diseño técnico, ADRs, estructura | Claude Code |
| `needs:images` | La tarea genera imágenes | Claude Code |
| `engine:claude`, `engine:codex`, `engine:gemini` | **Forzado manual** del motor; manda sobre todo lo demás | Eduardo o Claude Code |

`scripts/sync-labels.sh` y `github/labels.txt` suman las etiquetas nuevas.

## 4. Asignación

### 4.1 Puesto preferido y respaldo

| Tarea | Preferido | Respaldo, en orden | ¿Espera al preferido si está ocupado? |
|---|---|---|---|
| Dev con `kind:architecture` o `size:L` | `claude-senior` | `codex-senior` | Sí. Pasa al respaldo solo si el preferido está agotado por más de 2 h |
| Dev `size:S` o `size:M` | `codex-senior` | `gemini`, `claude-senior` | Sí, por la misma regla |
| Dev con `needs:images` | `codex-senior` | `gemini` | Sí, por la misma regla |
| Review | Otro motor que el del dev: `claude-senior` revisa a Codex y a Gemini; `codex-senior` revisa a Claude | Cualquier puesto de **otro motor** que el del dev | No: usa el respaldo enseguida |
| QA | `gemini` | `codex-senior`, `claude-senior` | No |
| Fix | El puesto del motor que programó (`engine:*` del PR) | Cualquier otro | No |
| Docs | `codex-senior` | `gemini`, `claude-senior` | No |

- **`engine:<motor>` en el issue o el PR** fija el motor y anula la tabla. Si ese motor está agotado, la tarea espera.
- **Al terminar un dev,** el PR recibe `engine:<motor del puesto>`, como hoy, para que la review sea de otro motor.

### 4.2 Prioridad: terminar antes de empezar

Cuando hay un puesto libre, el dispatcher elige entre las tareas que ese puesto puede tomar, en este orden:
1. Comentarios `@openhands`.
2. Conflictos.
3. Fix.
4. Review.
5. QA.
6. Dev y docs nuevos.

Dentro del mismo tipo, va primero el número más bajo. Las dependencias (`Depende de #N`), `needs:human`, los borradores y el máximo de rondas siguen como hoy.

## 5. Respaldo por límite de uso

### 5.1 Detección

Cuando una conversación termina con error, el dispatcher busca en la última respuesta patrones de límite. Estos son los que ya vimos:
- `You've hit your usage limit … try again at <hora>` (Codex), con formato `10:38 PM` o `Oct 12th, 2026 12:39 AM`;
- `You've hit your session limit · resets <hora> (UTC)` (Claude);
- `RESOURCE_EXHAUSTED` y `429` (Gemini).

Una función pura toma el texto y devuelve "es un límite" y "hasta cuándo".
- **Hora sin zona:** se interpreta en la zona del contenedor del dispatcher, configurable con `LIMIT_TZ` (por defecto `America/Argentina/Buenos_Aires`).
- **Sin hora:** se usa 1 hora.
- **Margen:** a la hora del reinicio se le suman 5 minutos.

### 5.2 Qué hace

1. El puesto queda **agotado hasta** esa hora, guardado en `state.json` (`slot_exhausted_until`).
2. La tarea **vuelve a la fila** con su label disparador original. No se pone `needs:human` y no cuenta como una ronda de review o QA. El agente que la retome sigue sobre la misma rama y el mismo PR.
3. **Un solo comentario** en el issue o PR: "`<puesto>` se quedó sin cupo (hasta las HH:MM UTC); la tarea vuelve a la fila". Es genérico, porque al terminar la tarea todavía no se sabe qué puesto la va a retomar.
4. **Nunca se asigna** una tarea a un puesto agotado.
5. **Si los patrones no reconocen el error,** se escala como hoy (`needs:human` con la respuesta citada), y el patrón nuevo se suma después.

## 6. Métricas

- **`pilot/metrics.csv`:** suma la columna `puesto`. Las filas viejas quedan con el puesto vacío.
- **`pilot/limits.csv`** (nuevo): `puesto, motor, detectado, hasta, tarea, mensaje` (el mensaje recortado a 200 caracteres).
- **Gasto de la API de Gemini:** al terminar cada tarea, el dispatcher cuenta en los eventos de la conversación (API de Canvas) las llamadas a `generate_image` del MCP `image` y las guarda en una columna `imagenes_gemini` de `metrics.csv`. La fase 5b estima el gasto con el precio por imagen configurado (`GEMINI_IMAGE_USD`, por defecto 0,04).
- **Funciones de agregación puras** (las usa la fase 5b), por puesto, para 24 h, 7 días y 30 días:
  - tareas y minutos;
  - uso: minutos ocupado sobre minutos del período;
  - horas agotado y cantidad de cortes;
  - retrabajo: rondas de fix y QA por issue, también por motor;
  - costo: el fijo prorrateado más el de la API, y el costo por issue cerrado.
- **Tiempos del flujo** (de que se crea el issue al PR listo, del PR listo al merge y de punta a punta): se calculan en la fase 5b a partir de GitHub. Este spec solo garantiza que las métricas tengan número, repo y fechas.

## 7. Reglas de decisión

Las calcula una función pura sobre los agregados, y la fase 5b las muestra:
- **Subir de nivel o sumar un semi senior:** un puesto agotado más de 2 h por día en 3 de los últimos 5 días hábiles.
- **Bajar de nivel:** un puesto con menos del 20 % de uso en los últimos 7 días.
- **Revisar el tamaño de las tareas:** más de 2 rondas de fix y QA por issue en promedio durante 7 días.

## 8. Cambios por componente

| Componente | Cambio |
|---|---|
| `config.py` | `SLOTS`, `SLOT_COST_*`, `LIMIT_TZ`, `GEMINI_IMAGE_USD`; `ENGINES` suma `gemini`; `ENGINE_AGENT_SETTINGS` para gemini |
| `models.py` | `Slot` (`name`, `engine`, `tier`); `ActiveTask.slot` |
| `decide.py` | Asignación por puesto (4.1), prioridad (4.2) y filtro de puestos agotados; ocupación por puesto en lugar de por motor |
| `limits.py` (nuevo) | Detección de límites y cálculo de la hora (5.1); funciones puras |
| `outcomes.py` | Una tarea cortada por límite vuelve a la fila sin `needs:human` (5.2) |
| `runner.py` y `state.py` | `slot_exhausted_until`, el comentario único y la columna `puesto` |
| `metrics.py` | Columnas `puesto` e `imagenes_gemini`, `limits.csv` y agregaciones (6 y 7) |
| `canvas/Dockerfile` | Gemini CLI con versión fijada, si la prueba sale bien |
| `roles/*.md` | Sin cambios de fondo; el QA pasa a correr en Gemini |
| `README`, `docs/nuevo-proyecto.md` y `github/labels.txt` | Puestos, etiquetas nuevas y cómo sumar un puesto |

## 9. Pruebas

- **Tests unitarios** de:
  - la detección de límites, con los mensajes reales de la sección 5.1 y variantes;
  - la asignación (tabla 4.1 completa, forzado con `engine:*`, puestos agotados, espera o respaldo);
  - la prioridad (4.2);
  - el reencolado sin `needs:human`;
  - las agregaciones y las reglas de decisión.
- **Lo que tiene que seguir pasando:** los 227 tests actuales, ajustando los que asumen un puesto por motor.
- **Prueba en la mini-PC:**
  1. Simular el agotamiento de un puesto cargando `slot_exhausted_until` a mano y verificar que la tarea vaya al respaldo.
  2. Correr un issue chico de nikito de punta a punta con los tres puestos.

## 10. Despliegue

1. **Prueba de Gemini CLI** (2.2). Con el resultado se decide si el puesto `gemini` entra.
2. **Credenciales nuevas,** cuando Eduardo las pase:
   - login de Claude con la cuenta Max 5x;
   - `CODEX_AUTH_JSON` de la cuenta Pro;
   - login de Gemini Pro.

   Se cargan por SSH, nunca por chat.
3. **Merge del dispatcher;** `git pull`; reconstruir `canvas` y `dispatcher` sin tareas activas.
4. **Etiquetas nuevas** en los repos, con `sync-labels.sh`.
5. **Bitácora,** y el README actualizado.

## 11. Fuera de alcance

- La pantalla de estado nueva (fase 5b).
- Los puestos semi senior y varias cuentas del mismo motor a la vez (2.1).
- Un coordinador automático que parta las épicas: la planificación sigue entre Eduardo y Claude Code.
- Gemini como reviewer: por ahora revisan Claude y Codex. Se reevalúa con las métricas de retrabajo.
