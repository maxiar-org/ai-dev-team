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
exec tini -- /opt/agent-canvas/entrypoint.sh "$@"
