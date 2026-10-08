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
# La imagen base trae el usuario node (1000:1000); se elimina para que UID/GID puedan ser 1000.
# El acceso a docker.sock se da con group_add en el compose (GID del grupo docker del host).
RUN userdel -r node \
 && groupadd -o -g ${GID} aidev && useradd -m -o -u ${UID} -g ${GID} -s /bin/bash aidev
# Versión fija y sin autoupdate: el binario es de root y el usuario aidev no puede actualizarlo.
ENV DISABLE_AUTOUPDATER=1
COPY --chmod=755 start.sh /usr/local/bin/operador-start
USER aidev
WORKDIR /opt/ai-dev-team
CMD ["/usr/local/bin/operador-start"]
