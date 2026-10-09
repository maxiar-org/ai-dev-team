# Fase 4e: resumen del operador a pedido (diseño)

- **Fecha:** 2026-10-09
- **Autor:** Eduardo Jiménez (con Claude)
- **Estado:** diseño aprobado en conversación, pendiente de revisión escrita
- **Antecedentes:** la 4d dejó `estado.maxiar.dev` armado con reglas fijas y un recuadro reservado ("Próximamente: resumen narrativo a pedido"). Este diseño es la opción C.

## 1. Objetivo

Un botón en `estado.maxiar.dev` que le pide al **operador** (Claude Code con la cuenta de Eduardo) un resumen narrativo con dos partes:

1. **Qué pasó** desde el resumen anterior (o en las últimas 24 h si es el primero).
2. **Qué hacer y por qué:** de 3 a 5 acciones priorizadas, cada una con su link y su razón.

### Criterios de éxito

1. Al apretar **"Pedir resumen"**, en 3 minutos o menos aparece el resumen en la sección "🤖 Resumen del operador", con su fecha y el período que cubre.
2. El segundo resumen cubre solo lo ocurrido desde el primero.
3. Mientras se genera, la página muestra "generando… hace X s" y no permite lanzar otro.
4. Con el operador apagado, o si `claude` falla, la sección muestra el error y el último resumen bueno. El resto de la página no cambia.
5. Desde el contenedor de Canvas (los agentes) no se puede pedir un resumen: no hay red y falta el token. El `claude -p` del resumen no puede escribir, ni usar `docker`, ni leer archivos.

## 2. Decisiones

| Tema | Decisión |
|---|---|
| Quién escribe | El **operador**, con `claude -p` en su contenedor (cuenta de Eduardo y su `CLAUDE.md`) |
| Contenido | Qué pasó desde T, más qué hacer y por qué. **Sin preguntas libres** desde la página |
| Datos | Los junta `estado` sin LLM y los manda como datos. El operador puede ampliar con comandos de `gh` de solo lectura |
| Período | T es la fecha del último resumen guardado, o 24 h atrás si no hay ninguno |
| Persistencia | Archivos en `~/resumenes/` del volumen `operador-home` (un JSON por resumen) |
| Programado (cada mañana) | Fuera de alcance; se puede agregar después |

## 3. Experiencia

- La sección muestra el último resumen: la fecha de generación, el período ("desde 08/10 21:14") y el texto en markdown convertido a HTML.
- Debajo hay un botón **"Pedir resumen"**, que es un formulario POST a `/resumen` de `estado`.
  - Responde con una redirección 303 a `/`.
  - Mientras hay un resumen en curso, el botón se reemplaza por "generando… hace X s" y la página se recarga cada 10 s en lugar de cada 60 s.
- Si el último intento falló, la sección muestra "⚠️ el último pedido falló: motivo" sobre el último resumen bueno.

## 4. Arquitectura

```
navegador ──POST /resumen──▶ estado ──POST /resumen (Bearer token)──▶ operador:8091 (resumen.py)
 (Access)                    junta datos desde T                     claude -p, prompt fijo
                             ◀──GET /resumen (estado y último resumen)─ ~/resumenes/*.json
```

### 4.1 `estado` (dispatcher/estado.py y view.py)
- **`POST /resumen`:**
  - verifica que `Origin` (o `Referer`) sea `https://estado.maxiar.dev`; si no, responde 403;
  - pregunta al operador desde cuándo resumir (`GET /resumen` → `since`);
  - junta los datos de ese período;
  - hace `POST` al operador con el JSON de datos;
  - redirige a `/`.
- **Datos del período**, todos de solo lectura:
  - la vista actual: lo que espera a Eduardo, el trabajo en curso, los despliegues, la salud y el consumo;
  - de GitHub: PRs mergeados (`search/issues`: `org:maxiar-org is:pr is:merged merged:>=T`) e issues cerrados en el período;
  - de `metrics.csv`: filas con `fin >= T` (rol, repo#número, motor, resultado y minutos);
  - de `[ops]`: alertas abiertas o cerradas en el período.
- **En cada ciclo de 60 s**, la vista consulta `GET /resumen` del operador y lo muestra. Si falla, la sección pone "sin datos (motivo)".
- **Markdown → HTML:** se escapa todo primero y después se convierten solo `##`/`###`, listas `-`, `**negrita**` y links `[texto](https://…)`. Cualquier otro esquema de link queda como texto.

### 4.2 Operador (`operador/resumen.py`, Python estándar 3.11)
- Es un servidor HTTP en `0.0.0.0:8091`, solo en la red `resumen`. `start.sh` lo lanza en segundo plano.
- Todo pedido sin `Authorization: Bearer $RESUMEN_TOKEN` recibe 401.
- **`GET /resumen`** devuelve `{status, since, started_at, last: {generated_at, since, markdown} | null, error}`.
  - `status` es `idle` o `running`.
  - `since` es el `generated_at` del último resumen bueno, o 24 h atrás.
- **`POST /resumen`:**
  - si hay uno en curso, responde 409;
  - si no, guarda los datos recibidos y lanza un hilo que ejecuta `claude -p` con el prompt fijo, y los datos en un bloque delimitado como "datos, no instrucciones";
  - responde 202.
- **Ejecución de `claude -p`:**
  - `--output-format text`;
  - `--max-turns 15`;
  - `--allowedTools` limitado a `Bash(gh issue view:*)`, `Bash(gh issue list:*)`, `Bash(gh pr view:*)`, `Bash(gh pr list:*)`, `Bash(gh pr diff:*)` y `Bash(gh run view:*)`;
  - `--disallowedTools` con `Read`, `Edit`, `Write`, `Glob`, `Grep`, `WebFetch`, `WebSearch` y `Bash(docker:*)`;
  - `cwd` en un directorio vacío;
  - timeout de 5 minutos.
- **Resultado:** si sale bien, se guarda `~/resumenes/<generated_at>.json`. Si falla, se guarda el error en memoria y se devuelve en `error`.
- **Prompt fijo:**
  - en español rioplatense, con las dos secciones obligatorias;
  - de 3 a 5 acciones con link;
  - sin inventar: si algo no está en los datos ni en `gh`, lo dice;
  - como máximo unas 300 palabras.

### 4.3 Compose y configuración
- **Red nueva `resumen`** (`internal: true`), compartida solo por `estado` y `operador`. Canvas y el dispatcher no la ven.
- **`RESUMEN_TOKEN`** en `.env` (generado con `openssl rand -hex 32`), pasado solo a `estado` y `operador`.
- `estado` recibe `RESUMEN_URL=http://operador:8091` y `ESTADO_ORIGIN=https://estado.maxiar.dev`.

## 5. Errores

| Caso | Comportamiento |
|---|---|
| El operador está caído o no responde | La sección muestra "sin datos (motivo)", y el botón se muestra igual. Si el POST falla, la redirección lleva `?error=` y la página muestra el motivo una vez |
| `claude` falla, se queda sin cuota o pasa el timeout | `status: idle` con `error`; la sección muestra el error y el último resumen bueno |
| Un segundo POST con uno en curso | El operador responde 409; `estado` redirige sin error, porque ya está generando |
| El operador se reinicia a mitad de un resumen | Se pierde el pedido en curso (`status` vuelve a `idle`); los resúmenes guardados quedan |

## 6. Fuera de alcance

- Preguntas libres desde la página.
- Resúmenes programados.
- Historial navegable de resúmenes; los archivos quedan en el volumen, por si hacen falta.

## 7. Riesgos

| Riesgo | Mitigación |
|---|---|
| Inyección de instrucciones desde títulos o comentarios de GitHub hacia un Claude con la cuenta de Eduardo | Prompt fijo con los datos delimitados como datos; herramientas limitadas a lectura de `gh`; sin `docker`, sin archivos y sin red web |
| Que alguien de la red local o los agentes disparen resúmenes | Red interna dedicada, token y verificación de `Origin`; además, Access delante de `estado` |
| Consumo de cuota | Solo a pedido, de a uno por vez, con tope de turnos |
