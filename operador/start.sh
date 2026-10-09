#!/bin/sh
# Mantiene una sesión tmux "operador" con Claude Code en Remote Control. Si claude termina, lo relanza.
set -e
git config --global --replace-all safe.directory /opt/ai-dev-team
# Instrucciones y skills del operador: viven en el repo (operador/claude) y se copian al HOME del contenedor.
mkdir -p "$HOME/.claude/skills"
cp /opt/ai-dev-team/operador/claude/CLAUDE.md "$HOME/.claude/CLAUDE.md"
cp -R /opt/ai-dev-team/operador/claude/skills/. "$HOME/.claude/skills/"
# Servidor de resúmenes a pedido (fase 4e): solo si hay token. Si se cae, se relanza.
if [ -n "$RESUMEN_TOKEN" ]; then
  sh /opt/ai-dev-team/operador/resumen-loop.sh &
fi
while true; do
  if ! tmux has-session -t operador 2>/dev/null; then
    tmux new-session -d -s operador -c /opt/ai-dev-team "claude --remote-control operador; sleep 5"
  fi
  sleep 30
done
