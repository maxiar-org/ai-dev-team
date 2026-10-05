---
title: Lecciones del piloto
description: Resultados, consumo, problemas encontrados y próximas fases del piloto.
sidebar:
  order: 1
---

Antes de construir el equipo completo (con QA y docs) se corrió un piloto de un fin de semana con solo dos roles
(dev y reviewer), sobre un proyecto real. El reporte completo está en
[`pilot/REPORT.md`](https://github.com/maxiar-org/ai-dev-team/blob/main/pilot/REPORT.md); esta página es su
resumen. El detalle día por día —incluidos los problemas de infraestructura y las decisiones de arquitectura— está
en la [bitácora](https://github.com/maxiar-org/ai-dev-team/blob/main/docs/bitacora.md).

- **Período:** 2026-10-03 al 2026-10-05, un fin de semana, en ratos libres.
- **Proyecto piloto:** [`qr-generator`](https://github.com/maxiar-org/qr-generator), un generador de QR para
  cartelería de comercios.
- **Setup:** OpenHands Agent Canvas en Docker. Dev con Codex (ChatGPT Plus), reviewer con Claude Code (Claude Pro),
  vía ACP. Un dispatcher propio orquestó todo desde GitHub.

## Resultados

| Criterio | Resultado |
|---|---|
| **A. Entrega autónoma** | ✅ 8 de 8 issues de producto terminaron en un PR mergeado **sin código de Eduardo** |
| **C. Consumo sostenible** | ✅ Todo el fin de semana usó el **25 %** del límite semanal de ChatGPT Plus y el **7 %** del de Claude Pro. No se topó ningún límite |
| **E. Entregables visibles** | ✅ App funcionando en una URL pública HTTPS (túnel), 3 documentos de investigación, capturas de Playwright por PR y README con instrucciones |

**Recomendación del piloto: seguir con la fase de equipo.** El modelo funciona y es sostenible con suscripciones.
Las intervenciones de Eduardo fueron de producto (aprobar, decidir) o detectaron problemas de proceso que ya se
corrigieron.

### A. Entrega autónoma

8 issues de producto pasaron por dev → review (con hasta 2 rondas de cambios) → PR mergeado, con **0 líneas de
código escritas por Eduardo**. Hubo 2 rondas de review con cambios (ambas resueltas sin intervención) y 1
escalamiento a `needs:human` (un fix llegó al límite de 60 minutos, pero el commit había subido 30 segundos antes
del corte). Las intervenciones de Eduardo, más allá de aprobar y mergear, fueron:

1. Dos comentarios `@openhands` para resolver conflictos — **ya no hacen falta**, ahora el dispatcher los resuelve
   solo (ver [El flujo del equipo](/ai-dev-team/guia/flujo-del-equipo/#conflictos-automáticos)).
2. Reetiquetar un issue después de un timeout.
3. **Detectar a mano una regresión real:** al resolver un conflicto, el agente desconectó dos pantallas que ya
   funcionaban en `main`. Se corrigió con un issue de bug, y se cambió el proceso para que no vuelva a pasar — ver
   [Problemas encontrados](#problemas-encontrados-y-cómo-se-resolvieron).

### C. Consumo

| Motor | Tareas | Máx. en 5 h | Min. promedio | Min. totales | Costo equivalente a API |
|---|---|---|---|---|---|
| Codex (ChatGPT Plus) | 16 | 7 | 4,4 | 68 | sin dato (Canvas no tiene el precio del modelo) |
| Claude (Claude Pro) | 15 | 8 | 9,7 | 145 | **USD 19,24** |

Con el mismo patrón de uso, una semana permitiría unas **4 veces** el trabajo de ese fin de semana antes de topar
Codex; Claude, usado sobre todo como reviewer, tiene mucho más margen. Pagando por uso, solo la parte de Claude
habría costado unos USD 19; con suscripciones el costo marginal fue cero. Codex resultó unas 2 veces más rápido que
Claude por tarea, pero Claude fue más exhaustivo como reviewer (probó la app en el navegador, buscó casos borde).

### E. Entregables visibles

| Tipo | Entregable |
|---|---|
| App corriendo | Contenedor Docker y URL pública HTTPS (Cloudflare Tunnel) probada en el iPhone |
| Documentos | Tres documentos de investigación (reseñas de Google, Mercado Pago, impresión directa) |
| Evidencia visual | Capturas de Playwright de los flujos principales, en el PR de un bug |
| Manual | README del proyecto piloto, con cómo correrlo y el flujo completo |

## Problemas encontrados y cómo se resolvieron

- **La API de Canvas aceptaba pedidos sin clave:** faltaba una variable de entorno en el compose para que el
  entrypoint la exportara. Se corrigió; ahora responde 401 sin clave.
- **Codex exponía los conectores de ChatGPT (Gmail) a los agentes:** se desactivaron.
- **Login de Codex y certificados:** Canvas no lee el login de Codex desde una variable de entorno (solo desde
  `~/.codex/auth.json`), y la imagen base no traía certificados raíz. Se agregó un script de inicialización y un
  volumen persistente para el login.
- **Regresión al resolver un conflicto:** un agente descartó funcionalidad de `main` para resolver un conflicto.
  Se corrigió el bug y se endurecieron las reglas del proceso: la resolución de conflictos tiene **prohibido**
  descartar funcionalidad de `main`; después de resolver conflictos el PR **vuelve a pasar por review**; el
  reviewer trata las regresiones como bloqueantes y recorre la UI; y se agregaron tests de integración de los
  flujos principales. Estas reglas son las que hoy aplican [dev, reviewer y fix](/ai-dev-team/guia/roles/).
- **Problemas de infraestructura** (login de Codex en volumen, certificados, `flutter` fuera del `PATH`, aprobación
  del token del bot en la organización, carrera del tablero con su automatización nativa): todos documentados y
  resueltos; el detalle día por día está en la bitácora.

En total, el dispatcher cerró el piloto con 132 tests automáticos.

## Riesgos que quedaron abiertos

- **Términos de uso de Anthropic:** Claude se usa vía ACP con la suscripción Pro (riesgo aceptado); hasta ahora sin
  problemas. El plan B es un modo híbrido con API key.
- **Sin aislamiento entre tareas:** todos los agentes comparten el contenedor de Canvas. Canvas tiene una opción de
  aislar el directorio de datos por conversación que vale la pena evaluar.

## Próximas fases

- **Fase 2 (equipo):** más roles —QA con Playwright y docs—, mejoras menores del dispatcher y un segundo proyecto
  real para validar que el setup se puede reutilizar. Esta fase ya está en marcha: los roles QA y docs que describe
  esta misma documentación nacieron acá.
- **Fase 3 (métricas):** consumo por ventana de 5 horas y semanal.
- **Fase 4 (mini-PC):** previews por PR (PaaS self-hosted + Cloudflare Tunnel), eventos de Canvas por webhook en
  lugar de consultar GitHub cada minuto, y un complemento visual propio de estado del proyecto que complemente al
  tablero Kanban.

## Documentos de diseño

El diseño y el plan detallado de cada fase son documentos de trabajo que no se publican en el sitio, pero quedan
en el repo y se pueden consultar:

- [Diseño del piloto](https://github.com/maxiar-org/ai-dev-team/blob/main/docs/superpowers/specs/2026-10-03-ai-dev-team-pilot-design.md)
  y su [plan](https://github.com/maxiar-org/ai-dev-team/blob/main/docs/superpowers/plans/2026-10-03-ai-dev-team-pilot.md).
- [Diseño de la fase 2 (QA y docs)](https://github.com/maxiar-org/ai-dev-team/blob/main/docs/superpowers/specs/2026-10-05-fase-2-qa-docs-design.md)
  y su [plan](https://github.com/maxiar-org/ai-dev-team/blob/main/docs/superpowers/plans/2026-10-05-fase-2-qa-docs.md).
