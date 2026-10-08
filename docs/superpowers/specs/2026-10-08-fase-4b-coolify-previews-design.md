# Fase 4b: Coolify y previews por PR (diseño)

- **Fecha:** 2026-10-08
- **Autor:** Eduardo Jiménez (con Claude)
- **Estado:** aprobado en conversación, pendiente de revisión escrita
- **Antecedentes:** fase 4a cerrada (`docs/bitacora.md`). El stack corre en la mini-PC con Cloudflare Tunnel y Access.

## 1. Objetivo

Que cada proyecto tenga **una versión estable pública** y **una preview por PR**, desplegadas solas en la mini-PC, para que Eduardo (y Maxi) prueben las entregas desde el celular sin construir nada a mano.

### Criterios de éxito

1. **Prueba acotada (`maxiar-org/preview-lab`)**, una app de compose con Postgres y Redis:
   - `main` se despliega solo en `preview-lab.maxiar.dev`;
   - un PR genera `preview-lab-pr-N.maxiar.dev` con **su propia base de datos**;
   - el link aparece en el PR;
   - al cerrar el PR, la preview y sus datos se borran.
2. `https://qr.maxiar.dev` sirve la versión de `main` de `qr-generator`, y se actualiza sola en cada merge.
3. Un PR de `qr-generator` recibe `https://qr-pr-N.maxiar.dev`, que se abre después del login de Access y desaparece al cerrar el PR.
4. Los puertos de Coolify no se ven desde la LAN. Solo se accede por el túnel.
5. Si Coolify se cae, el watchdog abre `[ops] coolify`.

## 2. Decisiones

| Tema | Decisión | Motivo |
|---|---|---|
| Instalación | **Instalador oficial de Coolify** en `/data/coolify` (segundo proyecto Compose) | Forma soportada y actualizable desde su panel. Sigue siendo todo Docker. Coolify maneja el host por SSH como `root`, con su propia clave, limitada a la mini-PC |
| Puertos | Panel en `127.0.0.1:8100` (el 8000 lo usa Canvas). Tiempo real en `127.0.0.1:6001/6002`. Proxy Traefik en `127.0.0.1:80/443` | Nada expuesto en la LAN; el TLS lo pone Cloudflare |
| Nombres | Estable: `<proyecto>.maxiar.dev`. Previews: **`<proyecto>-pr-N.maxiar.dev`** | El certificado Universal SSL de Cloudflare cubre un solo nivel (`*.maxiar.dev`). Dos niveles requieren Advanced Certificate Manager (USD 10 por mes) |
| Enrutamiento | Túnel `ai-dev-team`: `canvas.maxiar.dev` → Canvas, `coolify.maxiar.dev` → panel, `*.maxiar.dev` → `coolify-proxy:80` | Una sola puerta de entrada. Traefik reparte según el `Host` |
| Acceso | Access para `coolify.maxiar.dev` (salvo `/webhooks/*`) y para `*-pr-*` (las previews). `qr.maxiar.dev` pública | Las previews no quedan expuestas. GitHub puede llegar a los webhooks, y Coolify valida la firma |
| GitHub | GitHub App de Coolify en `maxiar-org`, instalada en `preview-lab` y `qr-generator`. Previews solo para PRs de miembros (no de forks) | Seguridad en repos públicos |
| QA | **Sin cambios en 4b:** sigue compilando en su contenedor | Decisión de Eduardo. QA sobre la preview queda para cuando haya proyectos con base de datos |

## 3. Componentes

### 3.1 Coolify
- Instalador oficial, con `APP_PORT=127.0.0.1:8100` y los puertos de tiempo real en `127.0.0.1`, ajustando `/data/coolify/source/.env` y reiniciando.
- Proxy Traefik con los puertos publicados solo en `127.0.0.1` (configuración del proxy en el panel de Coolify).
- "Servidor" `localhost`: la mini-PC.
- Dominios de las apps en `http://` (sin Let's Encrypt). Plantilla de URL de preview por app: `http://<proyecto>-pr-{{pr_id}}.maxiar.dev`. **A verificar en la prueba acotada:** que la plantilla acepte ese formato. Si no lo acepta, se evalúa la alternativa con Eduardo antes de seguir.

### 3.2 Túnel y Access (en el panel de Cloudflare, lo hace Eduardo)
- En el `docker-compose.yml` de ai-dev-team, `cloudflared` se suma a la red externa `coolify`.
- Public hostnames del túnel:
  - `coolify.maxiar.dev` → `http://coolify:8080`;
  - `*.maxiar.dev` → `http://coolify-proxy:80`;
  - `canvas.maxiar.dev` se mantiene y, al ser más específico, tiene prioridad.
- Aplicaciones de Access:
  - **Coolify** (`coolify.maxiar.dev`) con la política de Eduardo, más una aplicación **Coolify webhooks** (`coolify.maxiar.dev/webhooks`) con la política **Bypass**;
  - **Previews** (`*-pr-*.maxiar.dev`, o una por proyecto si Access no acepta ese comodín) con la política de Eduardo, y Maxi como opcional.

### 3.3 Prueba acotada: `maxiar-org/preview-lab`
- Repo público con una app mínima en Python (servidor HTTP de la librería estándar, sin dependencias externas) que cuenta visitas en Postgres y cachea en Redis. Muestra el nombre de la rama y el contador.
- `docker-compose.yml` con `app`, `postgres:17` y `redis:7`.
- Se despliega con el build pack "Docker Compose" de Coolify.

### 3.4 `qr-generator`
- App en Coolify con el build pack **Dockerfile** (el Dockerfile multi-stage existente: Flutter web → nginx).
- Dominio `http://qr.maxiar.dev` y previews `http://qr-pr-{{pr_id}}.maxiar.dev`.

### 3.5 Operación
- **Watchdog:** chequeo `coolify` con `GET http://coolify:8080/api/health` (el watchdog se suma a la red `coolify`). Mismo criterio de dos fallas seguidas.
- **`operador/claude/CLAUDE.md`:**
  - Coolify en `/data/coolify`, con su panel en `coolify.maxiar.dev`;
  - cómo ver despliegues y logs;
  - regla: no modificar `/data/coolify` ni los contenedores de Coolify sin confirmación de Eduardo.
- **README:** cómo sumar un proyecto (crear la app en Coolify, el dominio, la plantilla de preview y la aplicación de Access) y la mudanza (copiar `/data/coolify` y reinstalar).

## 4. Fuera de alcance

- QA sobre la preview (service token de Access).
- Bases de datos administradas por Coolify, backups de Coolify a S3 y producción en GCP.
- 4c (eventos de GitHub) y 4d (vista de estado).

## 5. Riesgos

| Riesgo | Mitigación |
|---|---|
| La plantilla de preview no acepta `<proyecto>-pr-{{pr_id}}` | Se detecta en la prueba acotada y se decide con Eduardo (otra convención o certificado avanzado) |
| Problemas conocidos de previews con compose (URL, red entre contenedores) | Para eso está la prueba acotada, antes de depender de Coolify |
| Access no acepta el comodín `*-pr-*` | Una aplicación de Access por proyecto (`qr-pr-*`) |
| Coolify usa RAM (alrededor de 1,5 GB) y disco por cada build | Hay 12 GB libres. Coolify tiene limpieza de imágenes; el watchdog vigila el disco |
| Coolify tiene SSH de `root` al host | Clave generada por Coolify, sin exposición externa (SSH no pasa por el túnel) |
| Mudanza: `/data/coolify` queda fuera del repo | Documentado en el README: copiar `/data/coolify` y correr el instalador |
