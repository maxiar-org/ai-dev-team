FROM python:3.12-slim

# Mismo UID/GID que el usuario "openhands" de Canvas: ambos escriben en /projects.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd -g 10001 openhands \
 && useradd -m -u 10001 -g 10001 openhands \
 && mkdir -p /projects /state /pilot /app \
 && chown -R 10001:10001 /projects /state /pilot /app

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

USER openhands
ENTRYPOINT ["python", "-m", "dispatcher"]
CMD ["run"]
