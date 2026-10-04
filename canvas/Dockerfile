# Agent Canvas con las herramientas que necesitan los agentes del piloto:
# Flutter (web + tests) y GitHub CLI. Los agentes ACP corren dentro de este contenedor.
FROM ghcr.io/openhands/agent-canvas:1.24.0

ARG FLUTTER_CHANNEL=stable

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl unzip xz-utils zip ca-certificates gnupg \
 && mkdir -p -m 755 /etc/apt/keyrings \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
 && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends gh \
 && rm -rf /var/lib/apt/lists/*

# Enlaces en /usr/local/bin: las shells de login reinician el PATH e ignoran el ENV de abajo.
RUN git clone --depth 1 --branch "${FLUTTER_CHANNEL}" https://github.com/flutter/flutter.git /opt/flutter \
 && chown -R openhands:openhands /opt/flutter \
 && ln -s /opt/flutter/bin/flutter /usr/local/bin/flutter \
 && ln -s /opt/flutter/bin/dart /usr/local/bin/dart

COPY --chmod=755 init-credentials.sh /usr/local/bin/init-credentials.sh
RUN mkdir -p /home/openhands/.codex && chown openhands:openhands /home/openhands/.codex

USER openhands
ENV PATH="/opt/flutter/bin:${PATH}"
RUN flutter config --no-analytics \
 && dart --disable-analytics \
 && flutter precache --web \
 && flutter --version

ENTRYPOINT ["/usr/local/bin/init-credentials.sh"]
