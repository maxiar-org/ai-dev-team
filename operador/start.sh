#!/bin/sh
# Mantiene una sesión tmux "operador" con Claude Code en Remote Control. Si claude termina, lo relanza.
set -e
git config --global --add safe.directory /opt/ai-dev-team
while true; do
  if ! tmux has-session -t operador 2>/dev/null; then
    tmux new-session -d -s operador -c /opt/ai-dev-team "claude --remote-control operador; sleep 5"
  fi
  sleep 30
done
