Antes de cualquier cambio o análisis, leer PROJECT_CONTEXT.md en la raíz del repositorio. Es el contexto canónico del proyecto: arquitectura, convenciones, decisiones de diseño y patrones obligatorios.

---

## Engram — Memoria persistente del equipo

Este workspace usa Engram como memoria persistente vía MCP (configurado en `.vscode/mcp.json`). Las memorias son compartidas entre todos los desarrolladores del equipo a través de Engram Cloud.

### PROTOCOLO AL INICIO DE CONVERSACIÓN (obligatorio)

**Al iniciar CADA conversación**, antes de responder el primer mensaje:

1. Llamar `mem_context` — carga el historial reciente de la sesión y contexto del proyecto.
2. Si el primer mensaje toca un tema específico (decisiones pasadas, estado del proyecto, bugs), también llamar `mem_search` con palabras clave relevantes.
3. Recién entonces componer la respuesta.

**Antes de responder cualquier pregunta sobre trabajo pasado o estado del proyecto** (incluso a mitad de conversación), llamar `mem_search` primero. Nunca asumir que no hay información — revisar Engram primero.

### CUÁNDO GUARDAR (obligatorio)

Llamar `mem_save` INMEDIATAMENTE después de cualquiera de estos eventos:

- Bug fix completado
- Decisión de arquitectura o diseño tomada
- Descubrimiento no obvio sobre el codebase
- Cambio de configuración o setup del entorno
- Patrón establecido (nombres, estructura, convención)
- Preferencia o restricción del usuario aprendida

Formato para `mem_save`:
- **title**: Verbo + qué — corto y buscable (ej: "Corregido N+1 en UserList", "Elegido Zustand sobre Redux")
- **type**: `bugfix` | `decision` | `architecture` | `discovery` | `pattern` | `config` | `preference`
- **scope**: `project` (default) | `personal`
- **topic_key** (recomendado para decisiones evolutivas): clave estable como `architecture/auth-model`
- **content**:
  ```
  **What**: Una oración — qué se hizo
  **Why**: Qué lo motivó (pedido del usuario, bug, performance, etc.)
  **Where**: Archivos o paths afectados
  **Learned**: Gotchas, edge cases, sorpresas (omitir si ninguno)
  ```

**Reglas de topic_key**: Reutilizar la misma `topic_key` para actualizar un tema en evolución en lugar de crear observaciones nuevas. Si hay duda, llamar `mem_suggest_topic_key` primero.

### PROTOCOLO AL CERRAR SESIÓN (obligatorio)

Antes de terminar una sesión o decir "listo" / "done", llamar `mem_session_summary` con esta estructura:

```
## Goal
[En qué estábamos trabajando esta sesión]

## Instructions
[Preferencias o restricciones del usuario descubiertas — omitir si ninguna]

## Discoveries
- [Hallazgos técnicos, gotchas, aprendizajes no obvios]

## Accomplished
- [Items completados con detalles clave]

## Next Steps
- [Qué queda por hacer — para la próxima sesión]

## Relevant Files
- path/to/file — [qué hace o qué cambió]
```

### CAPTURA PASIVA

Al completar una tarea, incluir una sección `## Key Learnings:` al final de la respuesta con items numerados. Engram los extrae y guarda automáticamente.

### Convenciones del equipo

| Regla | Detalle |
|---|---|
| Idioma de memorias `scope: project` | **Español** |
| Tipo para decisiones de arquitectura | `architecture` |
| Tipo para bugfixes | `bugfix` |
| Tipo para convenciones de código | `pattern` |
