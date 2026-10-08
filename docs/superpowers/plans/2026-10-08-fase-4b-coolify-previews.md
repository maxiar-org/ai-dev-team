# Fase 4b: Coolify y previews por PR (plan de implementación)

> **Para agentes que ejecuten este plan:** SUB-SKILL REQUERIDA: usar superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans para implementarlo tarea por tarea. Los pasos usan casillas (`- [ ]`) para seguir el avance.

**Objetivo:** instalar Coolify en la mini-PC detrás del túnel, validarlo con `preview-lab` (compose + Postgres + Redis) y desplegar `qr-generator` en `qr.maxiar.dev`, con previews `qr-pr-N.maxiar.dev`.

**Arquitectura:**
- Coolify (instalador oficial, `/data/coolify`) con sus puertos solo en `127.0.0.1`.
- `cloudflared` se suma a la red `coolify` y enruta `coolify.maxiar.dev` → `coolify:8080` y `*.maxiar.dev` → `coolify-proxy:80`.
- El watchdog suma el chequeo de la salud de Coolify.

**Stack:** Coolify v4, Traefik, Cloudflare Tunnel y Access, Docker Compose, Python 3.12 (watchdog, `preview-lab`), Postgres 17 y Redis 7.

**Spec:** `docs/superpowers/specs/2026-10-08-fase-4b-coolify-previews-design.md`

## Restricciones globales

- Nada de Coolify se publica en la LAN: todos sus puertos van en `127.0.0.1`.
- Nombres: `<proyecto>.maxiar.dev` para la versión estable y `<proyecto>-pr-N.maxiar.dev` para las previews. Los dominios de las apps se cargan en Coolify con `http://`.
- **La cuenta de administrador de Coolify se crea antes de exponer `coolify.maxiar.dev`** (por un túnel SSH), porque el primer visitante del panel es quien la crea.
- Las previews se despliegan solo para PRs de miembros de la organización.
- QA no cambia.
- No se toca `hermes` ni nada fuera de `ai-dev-team` y Coolify.

## Foco de revisión

1. **Coolify caído o reiniciándose:** el watchdog abre `[ops] coolify` solo si la falla se repite en dos ciclos seguidos. Test: `test_coolify_check_reports_health` (tarea 1).
2. **Sin URL de salud configurada** (por ejemplo, en una instalación sin Coolify): el chequeo `coolify` no aparece y no da falsas alertas. Test: `test_coolify_check_absent_when_not_configured` (tarea 1).
3. **Una preview que no se borra al cerrar el PR:** se verifica a mano en la tarea 6, paso 5.
4. **Las bases de datos de dos previews de `preview-lab` se mezclan:** se verifica en la tarea 6, paso 4, con contadores distintos.
5. **El 404 de Traefik para un subdominio inexistente** no debe filtrar información. Se verifica con `curl` en la tarea 6.

---

### Tarea 1: Chequeo de Coolify en el watchdog

**Archivos:**
- Modificar: `dispatcher/src/dispatcher/watchdog.py`, `docker-compose.yml`, `operador/claude/CLAUDE.md`, `README.md`
- Test: `dispatcher/tests/test_watchdog.py`

- [ ] **Paso 1: Tests que fallan:**

```python
def test_coolify_check_reports_health(tmp_path):
    hb = tmp_path / "hb"
    hb.write_text("1000")
    with respx.mock:
        respx.get("http://canvas:8000/api/conversations/count").respond(200, json=0)
        respx.get("http://coolify:8080/api/health").respond(502)
        checks = {c.name: c for c in run_checks("http://canvas:8000", "k", hb, "", str(tmp_path), now=1000.0,
                                                coolify_health_url="http://coolify:8080/api/health")}
    assert not checks["coolify"].ok and "502" in checks["coolify"].detail


def test_coolify_check_absent_when_not_configured(tmp_path):
    hb = tmp_path / "hb"
    hb.write_text("1000")
    with respx.mock:
        respx.get("http://canvas:8000/api/conversations/count").respond(200, json=0)
        checks = {c.name for c in run_checks("http://canvas:8000", "k", hb, "", str(tmp_path), now=1000.0)}
    assert "coolify" not in checks
```

- [ ] **Paso 2:** ejecutar `cd dispatcher && uv run pytest -q tests/test_watchdog.py`. Resultado esperado: FAIL (`unexpected keyword 'coolify_health_url'`).

- [ ] **Paso 3: Implementar.**
  - En `run_checks`, agregar el parámetro `coolify_health_url: str = ""` (después de `now`). Antes del chequeo de disco:

```python
    if coolify_health_url:
        try:
            resp = httpx.get(coolify_health_url, timeout=15)
            checks.append(Check("coolify", resp.status_code == 200, f"HTTP {resp.status_code}"))
        except httpx.HTTPError as exc:
            checks.append(Check("coolify", False, f"{type(exc).__name__}: {exc}"))
```

  - En `main()`, pasar `coolify_health_url=env.get("COOLIFY_HEALTH_URL", "")`.

- [ ] **Paso 4:** ejecutar `cd dispatcher && uv run pytest -q`. Resultado esperado: todo pasa.

- [ ] **Paso 5: Compose.**
  - En `cloudflared` y en `watchdog`, agregar `networks: [default, coolify]`.
  - En `watchdog`, agregar `COOLIFY_HEALTH_URL: ${COOLIFY_HEALTH_URL:-}`.
  - Al final del archivo:

```yaml
networks:
  coolify:
    external: true
    name: coolify
```

  - En `.env.example`, agregar `COOLIFY_HEALTH_URL=http://coolify:8080/api/health` con un comentario ("vacío si no hay Coolify").
  - **Ojo:** la red `coolify` la crea el instalador de Coolify. Hasta la tarea 3, el compose de la mini-PC no se redespliega.

- [ ] **Paso 6: Documentación.**
  - En `operador/claude/CLAUDE.md`, en Arquitectura, agregar "Coolify (`/data/coolify`, panel en `coolify.maxiar.dev`) despliega la versión estable y las previews de cada proyecto (`<proyecto>.maxiar.dev`, `<proyecto>-pr-N.maxiar.dev`)". En Reglas, agregar "9. No modifiques `/data/coolify` ni los contenedores `coolify*` sin confirmación de Eduardo; para despliegues usa el panel o su API".
  - En el `README`, agregar la sección "Coolify y previews":
    - sumar un proyecto: crear la app en Coolify, ponerle el dominio `http://<p>.maxiar.dev` y la plantilla `http://<p>-pr-{{pr_id}}.maxiar.dev`, y crear la aplicación de Access `<p>-pr-*`;
    - mudanza: copiar `/data/coolify` y correr el instalador.

- [ ] **Paso 7:** commit con el mensaje `feat: watchdog vigila Coolify; red coolify para el túnel`.

---

### Tarea 2: Repo `preview-lab`

**Archivos (repo nuevo `maxiar-org/preview-lab`, público):** `app.py`, `Dockerfile`, `docker-compose.yml`, `README.md`

- [ ] **Paso 1: `app.py`**, solo con la librería estándar más `psycopg` y `redis`, instalados en el Dockerfile:

```python
"""preview-lab: contador de visitas con Postgres y Redis para probar previews de Coolify."""
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import psycopg
import redis

DB = os.environ["DATABASE_URL"]
R = redis.Redis.from_url(os.environ["REDIS_URL"])
BRANCH = os.environ.get("BRANCH", "desconocida")


def init():
    with psycopg.connect(DB, autocommit=True) as c:
        c.execute("CREATE TABLE IF NOT EXISTS visitas (id serial primary key, en timestamptz default now())")


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok"); return
        with psycopg.connect(DB, autocommit=True) as c:
            c.execute("INSERT INTO visitas DEFAULT VALUES")
            total = c.execute("SELECT count(*) FROM visitas").fetchone()[0]
        R.incr("hits")
        body = f"<h1>preview-lab</h1><p>Rama: <b>{BRANCH}</b></p><p>Visitas en esta base: <b>{total}</b></p><p>Redis: {int(R.get('hits'))}</p>"
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(body.encode())


if __name__ == "__main__":
    init()
    HTTPServer(("0.0.0.0", 8080), H).serve_forever()
```

- [ ] **Paso 2: `Dockerfile`**

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir "psycopg[binary]==3.2.*" "redis==5.*"
COPY app.py /app.py
EXPOSE 8080
CMD ["python", "/app.py"]
```

- [ ] **Paso 3: `docker-compose.yml`**

```yaml
services:
  app:
    build: .
    environment:
      DATABASE_URL: postgresql://lab:lab@postgres:5432/lab
      REDIS_URL: redis://redis:6379/0
      BRANCH: ${COOLIFY_BRANCH:-local}
    depends_on: [postgres, redis]
    expose: ["8080"]
  postgres:
    image: postgres:17
    environment: {POSTGRES_USER: lab, POSTGRES_PASSWORD: lab, POSTGRES_DB: lab}
    volumes: [pgdata:/var/lib/postgresql/data]
  redis:
    image: redis:7
volumes:
  pgdata:
```

- [ ] **Paso 4: Verificación local** en la Mac: `docker compose up -d --build`, después `docker compose exec app python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8080/').read()[:120])"` dos veces (el contador sube), y `docker compose down -v`.

- [ ] **Paso 5:** crear el repo, hacer el primer commit, push, y proteger `main` igual que en los otros repos (exige PR y aprobación).

---

### Tarea 3: Instalar Coolify en la mini-PC

- [ ] **Paso 1:** ejecutar como `root`: `curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash`. El script instala en `/data/coolify` y crea la red `coolify`.
- [ ] **Paso 2: Puertos solo en localhost.**
  - En `/data/coolify/source/.env`, poner `APP_PORT=127.0.0.1:8100`, `SOKETI_PORT=127.0.0.1:6001` y, si existe, `REALTIME` o `TERMINAL` en `127.0.0.1:6002`.
  - Ejecutar `cd /data/coolify/source && docker compose --env-file .env -f docker-compose.yml -f docker-compose.prod.yml up -d` (los mismos archivos que usa el instalador).
  - Verificar con `ss -tlnp` que nada de Coolify escuche en `0.0.0.0` ni en `192.168.1.101`.
  - Si una variable no existe con ese nombre, revisar el compose de Coolify y anotar en el ledger cuál se usó.
- [ ] **Paso 3 👤: Cuenta de administrador antes de exponer.**
  1. Desde la Mac: `ssh -L 8100:127.0.0.1:8100 ubuntu-labs`.
  2. Eduardo abre `http://localhost:8100` y crea la cuenta de administrador (email y contraseña fuerte).
  3. Elige el servidor "localhost" y termina el onboarding.
- [ ] **Paso 4: Proxy en localhost.** En Coolify → Servers → localhost → Proxy:
  - en la configuración de Traefik, cambiar los puertos publicados a `127.0.0.1:80:80` y `127.0.0.1:443:443`, y quitar el `8080` público si está;
  - reiniciar el proxy;
  - verificar con `ss -tlnp` y `curl -s -o /dev/null -w "%{http_code}" -H "Host: nada.maxiar.dev" http://127.0.0.1/` (esperado: 404).
- [ ] **Paso 5: Redesplegar ai-dev-team** con la red `coolify`:
  - `git pull`;
  - agregar `COOLIFY_HEALTH_URL=http://coolify:8080/api/health` al `.env`;
  - `docker compose up -d --no-deps cloudflared watchdog`;
  - verificar en los logs del watchdog: `OK  coolify`.

---

### Tarea 4: 👤 Cloudflare: hostnames y Access

- [ ] **Paso 1:** en el túnel `ai-dev-team` → Public hostnames, agregar:
  - `coolify.maxiar.dev` → `HTTP` → `coolify:8080`;
  - `*.maxiar.dev` (comodín) → `HTTP` → `coolify-proxy:80`.

  Si el panel no crea solo el DNS comodín, agregar en DNS un `CNAME *` → `<id-del-túnel>.cfargotunnel.com` (proxied).
- [ ] **Paso 2:** crear aplicaciones de Access:
  1. **Coolify:** `coolify.maxiar.dev`, con la política de Eduardo.
  2. **Coolify webhooks:** `coolify.maxiar.dev`, ruta `webhooks`, con una política de **Bypass** (Include: Everyone).
  3. **Previews:** `*-pr-*.maxiar.dev`, con la política de Eduardo. Si Access rechaza ese comodín, crear `qr-pr-*.maxiar.dev` y `preview-lab-pr-*.maxiar.dev`.
- [ ] **Paso 3: Verificar desde la Mac:**
  - `curl -s -o /dev/null -w "%{http_code}" https://coolify.maxiar.dev/` da 302 (Access);
  - `https://coolify.maxiar.dev/webhooks/source/github/events` da un código distinto de 302;
  - `https://nada.maxiar.dev` da 404 del proxy.

---

### Tarea 5: 👤 GitHub App de Coolify

- [ ] **Paso 1:** en Coolify → Sources → `+ Add` → GitHub App:
  - organización `maxiar-org`;
  - Webhook Endpoint `https://coolify.maxiar.dev`;
  - "Register Now", que redirige a GitHub para crear la app;
  - instalarla en los repos `preview-lab` y `qr-generator`.
- [ ] **Paso 2:** verificar en Coolify que la Source quede en verde y liste los dos repos.

---

### Tarea 6: Prueba acotada con `preview-lab`

- [ ] **Paso 1:** en Coolify → Projects, crear `labs` → `+ New` → aplicación desde la GitHub App → `preview-lab`, rama `main`, build pack **Docker Compose**. Configurar:
  - en el servicio `app`, el dominio `http://preview-lab.maxiar.dev:8080`, o `http://preview-lab.maxiar.dev` con el puerto 8080 de la app, según la interfaz;
  - Preview Deployments: activadas; plantilla `{{pr_id}}`, ajustada para que la URL quede `http://preview-lab-pr-{{pr_id}}.maxiar.dev`;
  - Deploy.
- [ ] **Paso 2:** `curl -s https://preview-lab.maxiar.dev/` (pública en este momento) muestra "Rama: main" y un contador que sube.
- [ ] **Paso 3:** crear un PR en `preview-lab` (cambiar el título del HTML). Verificar:
  - Coolify despliega la preview;
  - aparece el link en el PR (comentario de la GitHub App de Coolify);
  - `https://preview-lab-pr-<N>.maxiar.dev` pide el login de Access.
- [ ] **Paso 4: Aislamiento.** Después del login de Eduardo, el contador de la preview empieza en 1 y es independiente del de `main`. Verificar desde la mini-PC con `docker ps --format '{{.Names}}' | grep -i pr` que haya un Postgres propio de la preview.
- [ ] **Paso 5: Limpieza.** Cerrar el PR y verificar que en unos minutos desaparezcan los contenedores y volúmenes de la preview (`docker ps -a`, `docker volume ls | grep -i pr`).
- [ ] **Paso 6:** si falla la plantilla de URL, la base aislada o la limpieza, **detenerse**, documentar en el ledger y en la bitácora, y consultar a Eduardo antes de la tarea 7.

---

### Tarea 7: `qr-generator` en Coolify

- [ ] **Paso 1:** en el proyecto `labs` (o uno nuevo, `qr-generator`), crear una aplicación desde la GitHub App → `qr-generator`, rama `main`, build pack **Dockerfile**. Configurar:
  - puerto expuesto: el que escucha nginx en el `Dockerfile` del repo (revisar `EXPOSE`);
  - dominio `http://qr.maxiar.dev`;
  - previews activadas con la plantilla `qr-pr-{{pr_id}}`;
  - Deploy.
- [ ] **Paso 2:** `curl -s https://qr.maxiar.dev/ | grep -o "<title>[^<]*</title>"` da "Generador de QR".
- [ ] **Paso 3:** con el próximo PR real de `qr-generator`, o con uno de prueba que cambie un texto, aparece `qr-pr-N.maxiar.dev`. Al cerrarlo, se borra.

---

### Tarea 8: Cierre

- [ ] **Paso 1:** con el watchdog, comprobar `[ops] coolify` como en la 4a: `docker stop coolify` y esperar la alerta. Después `docker start coolify` y verificar el cierre automático. **Solo con la confirmación de Eduardo**, porque deja el panel caído unos minutos.
- [ ] **Paso 2:** registrar en `docs/bitacora.md` los resultados de cada criterio, los ajustes a la plantilla y a Access, y los problemas encontrados. Actualizar la memoria del operador.
