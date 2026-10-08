# Operador del AI Dev Team: Claude Code con Remote Control, para operar el stack desde el celular.
FROM node:22-bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git tmux python3 gnupg procps \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin gh \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g @anthropic-ai/claude-code \
 && curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

ARG UID=1001
ARG GID=1001
ARG DOCKER_GID=999
RUN groupadd -g ${GID} aidev && useradd -m -u ${UID} -g ${GID} -s /bin/bash aidev \
 && (getent group docker || groupadd -g ${DOCKER_GID} docker) && usermod -aG docker aidev
COPY --chmod=755 start.sh /usr/local/bin/operador-start
USER aidev
WORKDIR /opt/ai-dev-team
CMD ["/usr/local/bin/operador-start"]
