# Guía de Agentes IA — Licitaciones Pi

## Agentes disponibles

Seleccioná el agente desde el picker de VS Code Copilot (ícono de agente en el chat) o escribí `@bmad-pm`, `@bmad-dev`, etc.

| Agente | Rol | Cuándo usarlo |
|--------|-----|---------------|
| `bmad-pm` | Product Manager | Definir qué construir: PRD, épicos, historias, sprint |
| `bmad-arq` | Arquitecto | Decidir cómo construirlo: arquitectura, tech decisions |
| `bmad-dev` | Desarrollador | Implementar: código, TDD, code review |
| `bmad-ui` | UX/UI Designer | Diseñar la experiencia: specs, flujos, componentes |
| `bmad-qa` | Test Architect | Garantizar calidad: tests, strategy, automation |
| `bmad-doc` | Tech Writer | Documentar: ADRs, índices, diagramas Mermaid |

---

## Flujo para agregar algo nuevo al proyecto

> El orden importa: UX y Arq informan las historias antes de que Dev toque código.

---

### Paso 1 — Definir el qué → `@bmad-pm`

Arrancá siempre con el PM. Creá el PRD y los épicos, pero **todavía no las historias individuales**.

| Seleccionar | Qué hace |
|-------------|----------|
| `PRD` | Crear o actualizar el documento de requerimientos |
| `CE` | Crear épicos y lista de historias *(sin bajar a detalle aún)* |

Artefactos guardados en `_bmad-output/planning-artifacts/`.

---

### Paso 2 — Diseñar la experiencia → `@bmad-ui` *(si tiene UI)*

Con los épicos como contexto, el UX diseña antes de que el PM escriba las historias.

| Seleccionar | Qué hace |
|-------------|----------|
| `CU` | Crear specs UX/UI para los épicos |
| `BS` | Brainstorming de componentes o flujos *(opcional)* |

Artefactos guardados en `design-artifacts/`.

---

### Paso 3 — Decidir la arquitectura → `@bmad-arq`

Con el PRD y las specs UX como base, el Arq define las decisiones técnicas.

| Seleccionar | Qué hace |
|-------------|----------|
| `CA` | Crear arquitectura y decisiones técnicas |
| `TR` | Investigación técnica sobre librerías o patrones *(opcional)* |

---

### Paso 4 — Crear las historias → `@bmad-pm`

Recién ahora, con UX y Arq como contexto, el PM escribe las historias y el sprint plan.

| Seleccionar | Qué hace |
|-------------|----------|
| `CS` | Crear historia individual lista para Dev |
| `SP` | Generar sprint plan |

Las historias van en `_bmad-output/planning-artifacts/stories/` ya con criterios de UI y restricciones técnicas incorporados.

---

### Paso 5 — Verificar alineación → `@bmad-pm` o `@bmad-arq`

Confirmar que PRD + UX + Arquitectura + Historias son consistentes. **No avanzar a dev hasta que pase.**

| Seleccionar | Qué hace |
|-------------|----------|
| `IR` | Implementation readiness check |

---

### Paso 6 — Implementar → `@bmad-dev`

Dev carga automáticamente las historias de `_bmad-output/planning-artifacts/stories/` y los specs de `design-artifacts/`.

| Seleccionar | Qué hace |
|-------------|----------|
| `DS` | Implementar una historia del sprint |
| `QD` | Quick dev: bug fix, tweak o feature pequeña |
| `CR` | Code review |
| `CP` | Checkpoint — revisión humana antes de merge |
| `DA` | Loop automático no asistido (una iteración completa) |

> **Git automatizado — no toques la terminal:**
>
> Al implementar una historia con `DS`, el agente hace todo el flujo git solo:
>
> | Momento | Qué hace Dev automáticamente |
> |---------|------------------------------|
> | Antes de escribir código | Detecta si estás en `main`/`develop` y crea `feat/<story-key>` desde `develop` |
> | Ya en rama de trabajo | Continúa sin crear rama nueva |
> | Al completar la historia | `git add -A` → `git commit` (formato Conventional Commits) → `git push` |
> | Después del push | Crea el PR a `develop` con el template y te muestra la URL |
>
> Solo intervenir si hay un conflicto que Dev no pueda resolver solo.  
> Con `QD` (cambios pequeños) el git **no** se automatiza — el commit y el PR los hacés vos.

---

### Paso 7 — Testear → `@bmad-qa`

| Seleccionar | Qué hace |
|-------------|----------|
| `TD` | Diseñar plan de tests para el épico |
| `AT` | Generar acceptance tests (ATDD) |
| `TA` | Expandir cobertura de tests |
| `GATE` | Release gate — auditoría final de calidad |

---

### Paso 8 — Documentar → `@bmad-doc` *(opcional)*

| Seleccionar | Qué hace |
|-------------|----------|
| `DP` | Documentar el proyecto (brownfield scan) |
| `WD` | Escribir un documento específico |
| `MG` | Generar diagrama Mermaid |
| `ID` | Actualizar índice de documentos |

---

## Dónde se guardan los artefactos

```
_bmad-output/
  planning-artifacts/
    prd.md                  ← PRD del proyecto
    epics.md                ← lista de épicos e historias
    architecture.md         ← decisiones de arquitectura
    stories/
      story-E1-H1.md        ← historias individuales para dev
      story-E1-H2.md
  implementation-artifacts/
    sprint-status.yaml      ← estado del sprint

design-artifacts/
  D-Design-System/          ← design system del proyecto
  [feature-name]-ux.md      ← specs UX por feature

docs/
  [tema].md                 ← documentación general
```

---

## Tips para pedidos efectivos

**Sé específico con el contexto:**
```
@bmad-pm "quiero agregar autenticación con Google OAuth al login, 
el PRD ya existe en _bmad-output/planning-artifacts/prd.md"
```

**Para features medianas o grandes, seguí el orden:**
`bmad-pm` → `bmad-ui` → `bmad-arq` → `bmad-dev` → `bmad-qa`

**Para bugs o cambios pequeños, ir directo a dev:**
```
@bmad-dev "hay un bug en el endpoint POST /analyses, devuelve 500 cuando..."
```

> Con cambios pequeños (menú `QD`) el git **no** se automatiza — Dev implementa el código pero el commit y el PR los hacés vos.

**Para dudas sobre qué hacer a continuación:**
```
@bmad-pm  →  menú "SS"  → ver estado del sprint y qué sigue
```

**Para investigar antes de decidir:**
```
@bmad-arq  →  menú "TR"  → investigación técnica sobre [tecnología]
```

---

## Estado del sprint

```
@bmad-pm  →  menú "SS"   → estado del sprint
@bmad-dev →  menú "SS"   → bloqueos activos
@bmad-qa  →  menú "SS"   → cobertura y calidad
```
