# Reporte del piloto AI Dev Team

- **Período:** 2026-10-03 al 2026-10-05 (un fin de semana, usado en ratos libres)
- **Proyecto piloto:** [`maxiar-org/qr-generator`](https://github.com/maxiar-org/qr-generator), un generador de QR para cartelería de comercios
- **Setup:** OpenHands Agent Canvas 1.24 en Docker en la Mac. Dev con Codex (ChatGPT Plus) y reviewer con Claude Code (Claude Pro, cuenta aparte), vía ACP. Un dispatcher propio orquesta todo desde GitHub.
- **Datos:** `pilot/metrics.csv` (31 tareas, de las cuales 29 son de `qr-generator`) y `docs/bitacora.md`

## Resumen

| Criterio | Resultado |
|---|---|
| **A. Entrega autónoma** | ✅ 8 de 8 issues de producto terminaron en un PR mergeado **sin código de Eduardo** |
| **C. Consumo sostenible** | ✅ Todo el fin de semana usó el **25 %** del límite semanal de ChatGPT Plus y el **7 %** del de Claude Pro. No se topó ningún límite |
| **E. Entregables visibles** | ✅ App funcionando en una URL pública HTTPS (túnel), 3 documentos de investigación, capturas de Playwright por PR y README con instrucciones |

**Recomendación: seguir con la fase 2.** El modelo funciona y es sostenible con suscripciones. Las intervenciones de Eduardo fueron de producto (aprobar, decidir) o detectaron problemas de proceso que ya se corrigieron.

## A. Entrega autónoma

| Issue | PR | Dev | Review | Notas |
|---|---|---|---|---|
| #1 Scaffold (Flutter, CI, Docker) | #9 | Codex 5,3 min | Claude 4,2 min | |
| #2 QR de WhatsApp | #10 | Codex | Claude ✅ | |
| #3 QR de Instagram | #11 | Codex | Claude ✅ | Conflictos con #10, resueltos con `@openhands` |
| #4 Diseño de impresión (58 mm) | #12 | Claude | Codex: CAMBIOS → fix → ✅ | El reviewer detectó un bloqueante real: faltaba el margen de seguridad del QR. Hubo conflictos dos veces |
| #5 Guardar imagen y WePrint | #15 | Codex | Claude ✅ | Esperó a #4 gracias a "Depende de" |
| #6 Google Reseñas | #13 | Codex | Claude ✅ | Conflictos resueltos automáticamente y revisados de nuevo |
| #7 Spike Mercado Pago | #14 | Codex 3,4 min | Claude 2,3 min | Solo documento |
| #17 Bug de regresión | #18 | Codex | Claude ✅ con Playwright | 11 capturas de Playwright en el PR |

- **Código escrito por Eduardo:** 0 líneas.
- **Rondas de review con cambios:** 2. En el #12 por el margen del QR y en el #16 (spike LPAPI). Las dos se resolvieron sin intervención.
- **`needs:human`:** 1. El fix del #12 con Claude tardó 60 minutos y llegó al timeout, pero el trabajo estaba completo: subió el commit 30 segundos antes del corte.

**Intervenciones de Eduardo**, además de aprobar y mergear:
1. Dos comentarios `@openhands` para resolver conflictos (#11 y #12). **Ya no hacen falta:** ahora el dispatcher resuelve los conflictos automáticamente.
2. Reetiquetar el #12 después del timeout.
3. **Detectó a mano una regresión:** al resolver un conflicto en el #12, Claude desconectó las pantallas de WhatsApp e Instagram. Se corrigió con el #17, y se cambió el proceso:
   - la resolución de conflictos tiene prohibido descartar funcionalidad de `main`;
   - después de resolver conflictos vuelve a revisar el agente;
   - el reviewer trata las regresiones como bloqueantes y recorre la UI con Playwright;
   - hay tests de integración de los flujos principales.

## C. Consumo

| Motor | Tareas | Máx. en 5 h | Min. promedio | Min. totales | Costo equivalente a API |
|---|---|---|---|---|---|
| Codex (ChatGPT Plus) | 16 | 7 | 4,4 | 68 | sin dato (Canvas no tiene el precio del modelo) |
| Claude (Claude Pro) | 15 | 8 | 9,7 | 145 | **USD 19,24** |

**Consumo real de las suscripciones** (dato de Eduardo, por todo el fin de semana):

| Suscripción | Límite semanal usado |
|---|---|
| ChatGPT Plus | 25 % |
| Claude Pro | 7 % |

- **Proyección:** con el mismo patrón de uso, una semana permitiría unas **4 veces** el trabajo de este fin de semana antes de topar Codex. Claude, usado sobre todo como reviewer, tiene mucho margen.
- **Comparación con pagar por uso:** solo la parte de Claude habría costado unos USD 19 a precio de API. Con suscripciones el costo marginal fue cero.
- **Codex es unas 2 veces más rápido** que Claude por tarea. Claude es más exhaustivo como reviewer (probó la app en el navegador, buscó casos borde), pero tuvo una tarea de 60 minutos.

## E. Entregables visibles

| Tipo | Entregable |
|---|---|
| App corriendo | Contenedor Docker (`docker build` y `docker run`), y URL pública HTTPS con Cloudflare Tunnel para probarla en el iPhone. Eduardo probó WhatsApp, Instagram y Reseñas y funcionan |
| Documentos | `docs/google-resenas.md`, `docs/mercado-pago.md` y `docs/impresion-directa.md` (PR #16) |
| Evidencia visual | `docs/issue-17/*.png`: capturas de Playwright de los flujos |
| Manual | README de `qr-generator` (cómo correrla, abrirla desde el iPhone y el flujo con WePrint) |

Correcciones de Eduardo sobre los entregables: ninguna, aparte de la regresión detectada (#17).

## Qué se construyó y corrigió en el AI Dev Team durante el piloto

- **Dispatcher:**
  - roles dev, reviewer y fix;
  - review cruzada entre motores;
  - límites (1 tarea por motor, 2 rondas, 60 minutos);
  - `@openhands` en comentarios y en reviews de PR;
  - **resolución automática de conflictos**;
  - **dependencias** con `Depende de #N`;
  - **tablero Kanban** de GitHub Projects sincronizado;
  - **MCP de Canvas** (Playwright) en las conversaciones;
  - métricas en CSV.

  En total, 132 tests.
- **Seguridad:**
  - La API de Canvas no exigía la clave; se corrigió.
  - Codex exponía los conectores de ChatGPT (Gmail) a los agentes; se desactivaron.
  - El token del bot nunca aparece en los comentarios.
  - `main` está protegida: exige PR, CI y la aprobación de Eduardo.
- **Problemas de infraestructura resueltos:** login de Codex en un volumen, certificados en los comandos de login, `flutter` en shells de login, aprobación del token del bot en la organización y la carrera del tablero con la automatización nativa.

## Riesgos que siguen abiertos

- **Términos de uso de Anthropic:** Claude se usa vía ACP con la suscripción Pro (opción C, riesgo aceptado). Hasta ahora no hubo problemas. El plan B sigue siendo el modo híbrido.
- **Sin aislamiento entre tareas:** todos los agentes comparten el contenedor de Canvas. Canvas tiene una opción `acp_isolate_data_dir` que vale la pena evaluar.
- Las mejoras menores diferidas de la revisión de código están listadas en la bitácora y en el ledger.

## Pendiente fuera del piloto

| Item | Tipo |
|---|---|
| #8 / PR #16: impresión directa LPAPI con la DT01 | Spike para probar en la Mac con Xcode y el iPhone |
| #19: Place ID automático desde la ubicación | Feature (probablemente requiere Google Places API, paga, y un backend) |
| #20: escanear el QR de Mercado Pago con la cámara | Feature |

## Propuesta para las próximas fases

- **Fase 2 (equipo):**
  - más roles: tester/QA con Playwright y docs;
  - aislamiento de tareas;
  - mejoras menores del dispatcher;
  - segundo proyecto real para validar que el setup se puede reutilizar.
- **Fase 3 (métricas):** consumo por ventana de 5 horas y semanal.
- **Fase 4 (mini-PC):**
  - **previews por PR** (Coolify o Dokploy + Cloudflare Tunnel);
  - **eventos de Canvas** por webhook;
  - **complemento visual** de estado del proyecto.

  Ver `docs/bitacora.md`.
