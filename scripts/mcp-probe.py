#!/usr/bin/env python3
"""Prueba un MCP server stdio: hace el handshake y lista sus herramientas.

Se corre dentro del contenedor de Canvas, que es donde lo van a lanzar los agentes:
  docker compose cp scripts/mcp-probe.py canvas:/tmp/mcp-probe.py
  docker compose exec -T canvas python3 /tmp/mcp-probe.py dart mcp-server
  docker compose exec -T canvas python3 /tmp/mcp-probe.py npx -y @playwright/mcp --headless --no-sandbox
"""

import json
import subprocess
import sys

if len(sys.argv) < 2:
    sys.exit(f"Uso: {sys.argv[0]} <comando> [args...]")

proc = subprocess.Popen(
    sys.argv[1:], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
)


def send(message: dict) -> None:
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()


def receive(request_id: int) -> dict:
    while True:
        line = proc.stdout.readline()
        if not line:
            sys.exit("El servidor terminó sin responder")
        message = json.loads(line)
        if message.get("id") == request_id:
            return message


try:
    send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "mcp-probe", "version": "0"}}})
    print("Servidor:", receive(1)["result"]["serverInfo"])
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = [tool["name"] for tool in receive(2)["result"]["tools"]]
    print(f"{len(tools)} herramientas:", ", ".join(tools))
finally:
    proc.kill()
