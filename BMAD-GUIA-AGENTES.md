# Guía de agentes BMAD — cómo agregar algo nuevo al proyecto

Este archivo explica el flujo completo para incorporar una nueva funcionalidad usando BMAD Method sobre GitHub Copilot Chat en VS Code.

---

## Dos tipos de skills — la diferencia clave

| Tipo | Ejemplos | ¿Aparece en el menú "Agent"? |
|---|---|---|
| **Agentes** (personas) | `bmad-agent-pm`, `bmad-agent-dev`, `bmad-agent-analyst` | Sí — se seleccionan desde el desplegable |
| **Workflows** (procesos) | `bmad-prd`, `bmad-architecture`, `bmad-help` | No — se invocan escribiendo `/bmad-nombre` en el chat |

**Regla fundamental:** cada workflow se corre en un **chat nuevo**. No encadenar varios workflows en la misma conversación.

---

## Cuándo usar cada agente

| Qué querés hacer | Agente a seleccionar |
|---|---|
| Definir qué construir (brief, requisitos) | `bmad-agent-analyst` o `bmad-agent-pm` |
| Diseño de pantallas / UX | `bmad-agent-ux-designer` |
| Arquitectura técnica | `bmad-agent-architect` |
| Implementar, revisar código, crear historias | `bmad-agent-dev` |

---

## Flujo completo para agregar algo nuevo

### Caso A: feature nueva sobre el MVP existente (lo más común)

El proyecto ya tiene PRD, arquitectura e historias. **No empezar de cero** — solo actualizar lo que corresponde.

**Paso 1 — Actualizar el PRD** *(chat nuevo, modelo Claude Opus)*
```
Agente: bmad-agent-pm
Skill:  /bmad-prd
Intención: Update  ← elegir esto, no "Create"
```
El agente pregunta qué alcance nuevo se agrega. Se describe la feature en lenguaje natural. Actualiza `prd.md` con los nuevos requisitos.

**Paso 2 — Actualizar arquitectura si es necesario** *(chat nuevo, Claude Opus)*
```
Agente: bmad-agent-architect
Skill:  /bmad-architecture
```
Solo si la feature implica un nuevo nodo, servicio o cambio estructural. Si es una pantalla o variación menor, se puede saltar.

**Paso 3 — Crear las historias nuevas** *(chat nuevo, Claude Opus)*
```
Agente: bmad-agent-pm
Skill:  /bmad-create-epics-and-stories
```
Genera las historias nuevas a partir del PRD actualizado. Se suman al `sprint-status.yaml` existente, no lo reemplazan.

**Paso 4 — Chequeo de coherencia** *(chat nuevo, Claude Sonnet — opcional pero recomendado)*
```
Agente: bmad-agent-architect
Skill:  /bmad-check-implementation-readiness
```
Valida que PRD, arquitectura e historias sean consistentes antes de programar.

**Paso 5 — Implementar historia por historia** *(se repite por cada historia)*

Cada historia sigue siempre el mismo ciclo de 3 pasos, cada uno en un chat nuevo:

```
Chat 1 — Crear la historia
  Agente: bmad-agent-dev
  Skill:  /bmad-create-story
  Modelo: Claude Opus si es compleja (ej. nodo de extracción)
          Claude Sonnet si es simple (ej. pantalla de frontend)

Chat 2 — Implementar
  Agente: bmad-agent-dev
  Skill:  /bmad-dev-story

Chat 3 — Revisar código
  Agente: bmad-agent-dev
  Skill:  /bmad-code-review
```

**Paso 6 — Cierre de épica**
```
Agente: bmad-agent-dev
Skill:  /bmad-retrospective
```
Al terminar todas las historias de una épica.

---

### Caso B: proyecto nuevo desde cero

Solo para cuando se empieza un producto completamente distinto. Secuencia completa en orden:

| # | Skill | Frecuencia |
|---|---|---|
| 1 | `/bmad-product-brief` | Una vez |
| 2 | `/bmad-prd` (intención: Create) | Una vez |
| 3 | `/bmad-ux` | Una vez |
| 4 | `/bmad-architecture` | Una vez |
| 5 | `/bmad-create-epics-and-stories` | Una vez |
| 6 | `/bmad-check-implementation-readiness` | Una vez |
| 7 | `/bmad-sprint-planning` | Una vez (arranca la implementación) |
| 8 | `/bmad-create-story` → `/bmad-dev-story` → `/bmad-code-review` | Una vez por historia |
| 9 | `/bmad-retrospective` | Al cerrar cada épica |

---

## Qué modelo usar en cada paso

| Paso | Modelo recomendado | Por qué |
|---|---|---|
| `bmad-product-brief`, `bmad-prd`, `bmad-architecture`, `bmad-create-epics-and-stories` | **Claude Opus** | Se corren una sola vez y definen todo lo que sigue |
| `bmad-check-implementation-readiness` | Claude Sonnet | Verificación, no creación |
| `bmad-create-story` (historias complejas, ej. nodo de extracción) | **Claude Opus** | Vale el modelo más fuerte para definir bien los criterios |
| `bmad-create-story` (historias simples, ej. pantallas) | Claude Sonnet | Bajo riesgo |
| `bmad-dev-story`, `bmad-code-review` | GPT-5.3 Codex | Especializado en código, corre muchas veces |
| `bmad-sprint-planning`, `bmad-retrospective` | Auto | Administrativo, bajo riesgo |

**Regla fácil:** cuanto más se arrastra el resultado (brief → PRD → arquitectura → historias), más conviene el modelo más fuerte. Cuanto más se repite (una vez por historia), más conviene Auto o el modelo de código.

---

## Cómo optimizar el cupo de Copilot

- Cada mensaje cuenta como una solicitud, sin importar el largo.
- Si el agente hace 3 preguntas, responderlas **todas en un solo mensaje**.
- Reservar Claude Opus solo para los pasos de planificación — no usarlo en `bmad-dev-story`.

---

## Dónde quedan los archivos generados

```
_bmad-output/
├── planning-artifacts/
│   ├── product-brief.md
│   ├── prd.md
│   ├── architecture.md
│   └── epics/          ← historias individuales
└── implementation-artifacts/
    └── sprint-status.yaml
```

---

## Referencia rápida

```
# Ver estado del sprint
/bmad-sprint-status

# Preguntar qué hacer a continuación
/bmad-help

# Buscar el próximo paso en el sprint
bmad-agent-dev → /bmad-sprint-planning
```
