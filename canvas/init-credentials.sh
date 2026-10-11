#!/bin/sh
# Materializa el login de Codex desde CODEX_AUTH_JSON la primera vez.
# ~/.codex vive en un volumen: las renovaciones del token que haga Codex se conservan
# entre reinicios. Para forzar un login nuevo: docker volume rm ai-dev-team_codex-home
set -e
auth="$HOME/.codex/auth.json"
if [ -n "${CODEX_AUTH_JSON:-}" ] && [ ! -s "$auth" ]; then
  mkdir -p "$HOME/.codex"
  umask 077
  printf '%s' "$CODEX_AUTH_JSON" > "$auth"
fi
# API key de Gemini para el MCP de imágenes: queda en un archivo privado que lee mcp-image-gemini.
if [ -n "${GEMINI_API_KEY:-}" ]; then
  mkdir -p "$HOME/.config/mcp-image"
  (umask 077; printf '%s' "$GEMINI_API_KEY" > "$HOME/.config/mcp-image/gemini_key")
fi
unset GEMINI_API_KEY
# Sin conectores de ChatGPT (Gmail, etc.): un agente que lee issues no debe tener acceso a ellos.
cfg="$HOME/.codex/config.toml"
mkdir -p "$HOME/.codex"
if ! grep -qs '^apps *= *false' "$cfg"; then
  printf '\n[features]\napps = false\n' >> "$cfg"
fi
exec tini -- /opt/agent-canvas/entrypoint.sh "$@"
