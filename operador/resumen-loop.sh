#!/bin/sh
# Relanza el servidor de resúmenes (fase 4e) si termina. Sin `set -e` a propósito: si el servidor sale con error
# (lo mataron, falló al arrancar), el bucle tiene que seguir. start.sh usa set -e, por eso esto va en un script aparte.
set +e
CMD=${RESUMEN_CMD:-"python3 /opt/ai-dev-team/operador/resumen.py"}
PAUSA=${RESUMEN_PAUSA:-5}
while true; do
  $CMD
  sleep "$PAUSA"
done
