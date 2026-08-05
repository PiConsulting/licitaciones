---

## story\_id: "2.10" story\_key: "2-10-prompts-alineados-diccionario-y-estados" epic: 2 title: "Prompts de extraccion alineados al contrato AD-12, al diccionario de datos y a los 4 estados del PRD" status: "draft" created: "2026-08-05" epic\_title: "Analisis de Pliegos (Subida \+ Extraccion \+ Progreso)"

# Story 2.10: Prompts de extracción alineados al contrato AD-12, al diccionario de datos y a los 4 estados del PRD

## User Story

Como Ejecutivo Comercial que decide si participar de una licitación a partir del análisis, quiero que cada prompt de extracción pida exactamente los campos que el PRD definió para su categoría, distinga "no encontrado" de "no aplica", y calibre la confianza según lo que el usuario puede hacer con ese campo, para que un campo vacío o con baja confianza en pantalla signifique algo confiable y no una limitación del prompt que nadie detectó.

## Por qué esta historia (tres gaps concretos, no una mejora genérica)

Revisando el contrato ya definido en Story 2.5 (**AD-12**) contra el PRD y contra el tipo de datos que ya usa el frontend en Story 3.1 (`status: "review"`, es decir, ya construido o en revisión), aparecen tres inconsistencias reales entre lo que el PRD promete y lo que el código va a hacer:

**1\. AD-12 no tiene los 4 estados que el PRD exige.** El contrato Pydantic de Story 2.5 define:

```py
extraction_status: Literal["success", "failed", "not_found", "partial"]
```

El PRD (§6.1) define **cuatro estados de campo**: Extraído, No encontrado, No aplica, En conflicto — con una regla explícita: *"marcar 'no aplica' por ausencia de evidencia es el error más peligroso"* (§6.1). AD-12 no tiene `not_applicable`. Sin ese estado, un prompt no tiene forma de decir "el pliego no exige esta garantía" — la distinción que el propio PRD marca como la más importante de todo el modelo de datos.

**2\. El tipo del frontend (Story 3.1) es más angosto todavía que AD-12.** En `3-1-visualizacion-de-resultados-por-categoria.md` (líneas 146 y 456):

```ts
extraction_status: 'success' | 'partial' | 'failed';
```

Ni siquiera incluye `'not_found'`, que sí existe en AD-12 y en el PRD desde el v1.1. Story 3.1 está en estado `review` — es decir, este hueco puede estar ya construido. Corregirlo después implica coordinar una migración de tipo, no sólo agregar un valor a un enum.

**3\. Los prompts actuales no piden los campos que el PRD define por categoría (§5.2).** Ejemplo concreto — el prompt de garantías (mostrado en Story 2.5 §9, e idéntico al que corre hoy en `backend/analysis/extraction/prompts/garantias.txt`) pide `tipo`, `monto_porcentaje`, `monto_valor`, `forma_constitucion`, `vigencia`. El diccionario del PRD (§5.2.3) además exige `sobre_que_se_calcula` (base del porcentaje: presupuesto oficial, monto ofertado, otro) y `plazo_constitucion` (distinto de `vigencia`) — ninguno de los dos se pide hoy, así que aunque estén en el pliego, el prompt nunca los va a extraer. La tabla de mapeo completa está más abajo.

Esta historia es distinta de "mejorar prompts en general": son tres contratos concretos (Pydantic AD-12, tipo TypeScript de 3-1, y el texto de los 8 `.txt`) que hoy no dicen lo mismo que el PRD, y hay que alinear los tres a la vez para que el estado no se pierda entre el backend y la pantalla.

## Acceptance Criteria

### AC1: Los 8 prompts piden los campos del diccionario de datos (§5.2)

**Given** el diccionario de datos por categoría del PRD (§5.2) **When** se revisa cada uno de los 8 prompts (`plazos.txt`, `garantias.txt`, `causales.txt`, `documentos_requeridos.txt`, `criterios_evaluacion.txt`, `restricciones_participacion.txt`, `cronograma_proceso.txt`, `estimacion_presupuesto.txt`) **Then** cada prompt pide exactamente los campos definidos para su categoría (ver tabla de mapeo más abajo), sin omitir ninguno.

### AC2: Contrato AD-12 soporta los 4 estados del PRD

**Given** el schema Pydantic `ExtractedItem` (`extraction_status: Literal[...]`) **When** se actualiza el contrato **Then** incluye `"not_applicable"` junto a `"success"`, `"not_found"`, `"failed"` (el estado "En conflicto" se sigue resolviendo a nivel de merge en la columna `conflicts`, según AC7 de Story 2.5 — no es un valor de `extraction_status` por ítem, y esta historia no lo cambia).

### AC3: Regla de "no aplica" con cita obligatoria

**Given** un prompt que evalúa si un requisito/garantía/plazo se exige **When** el pliego declara explícitamente que no se exige **Then** el prompt exige una cita textual de esa declaración para poder usar `extraction_status="not_applicable"`; sin esa cita, el resultado correcto es `"not_found"` — igual que ya quedó resuelto como ejemplo en `garantias.txt` (ver referencia).

### AC4: El tipo TypeScript de Story 3.1 incluye los 4 estados

**Given** el tipo `extraction_status: 'success' | 'partial' | 'failed'` en `3-1-visualizacion-de-resultados-por-categoria.md` **When** se corrige **Then** incluye `'not_found'` y `'not_applicable'`, y el componente que renderiza el badge de estado contempla los 5 valores posibles (`success | failed | not_found | partial | not_applicable`) sin caer a un estado por defecto incorrecto.

### AC5: Regla de fechas relativas en el prompt de plazos

**Given** el prompt `plazos.txt` **When** el pliego expresa un plazo de forma relativa ("10 días hábiles desde la notificación") **Then** el prompt instruye explícitamente no calcular la fecha resultante y exige conservar el texto original tal como aparece (campo `texto_original`, **siempre presente** según §5.2.4), además de `fecha`/`hora` sólo cuando el pliego los enuncia explícitamente.

### AC6: Citas de datos en tablas

**Given** un campo cuyo valor viene de una tabla (depende de Story 2.9 para que el chunk llegue con esa estructura) **When** el prompt arma `source_references` **Then** instruye citar encabezado de columna \+ fila, según §6.3.

### AC7: Calibración de confianza ligada a la semántica de acción del PRD

**Given** la tabla de niveles del PRD (§6.2: Alta \= usar sin abrir el documento, Media \= verificar antes de usar, Baja \= no usar sin leer el original) **When** cada prompt pide `confidence` **Then** incluye una guía explícita de rangos numéricos atados a esa semántica de acción, en vez de dejar `confidence` sin ningún criterio — hoy el único cálculo de confianza vive en `calculate_confidence` (Story 2.5 §11), una heurística de cantidad/longitud de citas que no tiene relación con lo que el usuario puede hacer con el dato.

### AC8: `tipo` como enum canónico para no romper la detección de conflictos

**Given** que `merge_node` (Story 2.5 §10) detecta conflictos comparando por igualdad exacta de string sobre `tipo` (`plazos_by_tipo[tipo]`, `garantias_by_tipo[tipo]`) **When** el LLM extrae `tipo` **Then** el prompt restringe `tipo` a una lista cerrada de valores canónicos (los definidos en §5.2 por categoría), no texto libre — de lo contrario, dos documentos que nombran la misma garantía con vocabulario distinto ("garantía de oferta" vs "garantía de mantenimiento de oferta") generan dos entradas separadas en el listado en vez de detectarse como el mismo ítem en conflicto o coincidencia, y el TODO ya reconocido en Story 2.5 ("Detección de conflictos semánticos \>85%") sigue sin resolverse.

## Tabla de mapeo prompt → diccionario PRD (§5.2)

| Prompt | Categoría PRD | Campos que hoy faltan |
| :---- | :---- | :---- |
| `garantias.txt` | 3\. Garantías (crítica) | `sobre_que_se_calcula`, `plazo_constitucion` (distinto de `vigencia`), moneda explícita |
| `plazos.txt` | 4\. Plazos clave (crítica) | expresión relativa, `texto_original` siempre presente, `prorrogable`, `lugar` |
| `causales.txt` | 6\. Causales de rechazo (crítica) | rechazo automático / sujeto a evaluación, `subsanable`, momento en que aplica |
| `documentos_requeridos.txt` | 2\. Requisitos de admisibilidad | tipo (legal/técnico/económico-financiero/administrativo/experiencia), `obligatorio`, momento de presentación, `subsanable` |
| `criterios_evaluacion.txt` | 5\. Criterios de evaluación | método de adjudicación, ponderación en %, fórmula de evaluación, puntaje técnico mínimo |
| `restricciones_participacion.txt` | probablemente \= 2\. Requisitos de admisibilidad, con otro nombre — **confirmar con PM antes de tocar este prompt** (ver Riesgos) | — |
| `cronograma_proceso.txt` | no mapea 1:1 a una categoría de §5.2 — **confirmar alcance con PM** (ver Riesgos) | — |
| `estimacion_presupuesto.txt` | parte de 8\. Datos del procedimiento | falta el resto completo: organismo convocante, número de expediente, número de procedimiento, tipo de procedimiento, jurisdicción — **hoy no hay extractor para esos campos** |

## Tareas / Subtareas

- [ ] T1: Confirmar mapeo de categorías dudosas antes de tocar esos dos prompts (AC1)  
        
      - [ ] 1.1 Resolver con PM si `restricciones_participacion.txt` y `documentos_requeridos.txt` son la misma categoría partida en dos nodos o dos cosas distintas.  
      - [ ] 1.2 Resolver a qué categoría de §5.2 mapea `cronograma_proceso.txt`, o si es una categoría operativa sin definición formal en el diccionario.  
      - [ ] 1.3 Decidir si "Objeto y alcance", "Anexos obligatorios" y el resto de "Datos del procedimiento" quedan fuera de esta historia (nodos nuevos, historia aparte).

      

- [ ] T2: Rediseñar los 6 prompts con categoría confirmada (AC1, AC3, AC5, AC6, AC7, AC8)  
        
      - [ ] 2.1 `garantias.txt` — ya tiene una versión de referencia aplicando este patrón completo.  
      - [ ] 2.2 `plazos.txt` — expresión relativa, texto original, prorrogable, lugar, sin cálculo de fechas.  
      - [ ] 2.3 `causales.txt` — rechazo automático/sujeto a evaluación, subsanable, momento.  
      - [ ] 2.4 `criterios_evaluacion.txt` — método, ponderación, fórmula, puntaje mínimo.  
      - [ ] 2.5 `estimacion_presupuesto.txt` — decidir alcance según T1.3.  
      - [ ] 2.6 `documentos_requeridos.txt` / `restricciones_participacion.txt` — según T1.1.  
      - [ ] 2.7 `cronograma_proceso.txt` — según T1.2.

      

- [ ] T3: Contrato AD-12 con 4 estados (AC2)  
        
      - [ ] 3.1 Actualizar `Literal["success", "failed", "not_found", "partial"]` para incluir `"not_applicable"` en el schema Pydantic de Story 2.5.  
      - [ ] 3.2 Actualizar la agregación de estado por categoría (donde hoy sólo se distingue éxito/no-éxito) para no colapsar `not_applicable` dentro de `not_found`.

      

- [ ] T4: Tipo TypeScript de Story 3.1 (AC4)  
        
      - [ ] 4.1 Actualizar el union type en los dos puntos donde aparece (líneas 146 y 456 del archivo de la historia).  
      - [ ] 4.2 Actualizar el componente de badge de estado para los 5 valores posibles.  
      - [ ] 4.3 Si Story 3.1 ya está implementada (status "review"), coordinar como fix/migración, no como parte "gratis" de esta historia — puede requerir su propia historia de bugfix.

      

- [ ] T5: Tests (AC1–AC8)  
        
      - [ ] 5.1 Un caso de prueba por categoría con el campo nuevo del diccionario que hoy falta.  
      - [ ] 5.2 Un caso `not_applicable` con cita explícita por categoría aplicable.  
      - [ ] 5.3 Un caso de conflicto de `tipo` con vocabulario distinto entre dos documentos, verificando que el merge lo detecta como el mismo ítem (no como dos ítems separados).

## Dev Notes

### Requerimientos de Arquitectura y Cumplimiento

- AD-12 es "contrato CRÍTICO" según Story 2.5 — cualquier cambio debe coordinarse con quien ya construyó sobre el contrato viejo (Story 3.1 en `review`), y puede requerir migración de datos si ya existen `analysis_versions` guardadas con el esquema anterior.  
- Respeta §5.2 (diccionario de datos), §6.1 (4 estados), §6.2 (confianza como nivel/acción), §6.3 (citas, incluida la regla de tablas) del PRD.  
- Depende de Story 2.11 (glosario) para el bloque `{sinonimos}` que cada prompt debería incluir — si 2.11 no está implementada, ese bloque queda vacío o con un texto fijo hasta que exista.  
- Depende de Story 2.9 para AC6 (citas de tabla) — sin chunks que preserven estructura de tabla, el prompt no tiene de dónde citar encabezado \+ fila.

### Guardrails de Implementación (Obligatorios)

- No romper el contrato de `state_field`/`status_field` que ya consumen frontend y merge: los campos nuevos se agregan, no se renombran campos existentes sin coordinar la migración.  
- No dejar `not_applicable` sólo en el prompt sin actualizar el schema Pydantic y el tipo TypeScript — los tres deben cambiar juntos o el estado se pierde en algún punto del pipeline.  
- No confundir "En conflicto" (nivel merge, columna `conflicts`) con un nuevo valor de `extraction_status` por ítem — el PRD lo define como uno de los 4 estados de campo, pero el mecanismo de detección ya vive aparte en `merge_node`; esta historia no lo mueve.

### Inteligencia de Historia Previa y Commits

- Story 2.5 definió AD-12 y los prompts base (texto casi idéntico al que corre hoy en el repo).  
- Story 3.1 (`review`) ya construyó/está construyendo sobre un tipo de estado más angosto que AD-12 — el gap identificado en el AC4 es objetivamente anterior a esta historia, no algo que esta historia introduce.  
- Story 2.9 (chunking con Document Intelligence) es prerequisito de AC6.  
- Story 2.11 (glosario) es prerequisito del bloque de vocabulario equivalente en cada prompt.

## Riesgos / Dudas a Validar Antes de Estimar

1. `restricciones_participacion.txt` vs `documentos_requeridos.txt`: sin resolver este mapeo, no se puede escribir un AC verificable para esos dos prompts — es un hueco de producto, no de implementación.  
2. `cronograma_proceso.txt` no tiene categoría clara en §5.2 — podría ser redundante con `plazos.txt` o cubrir algo genuinamente distinto (etapas del proceso vs fechas puntuales); confirmar antes de estimar.  
3. Cambiar AD-12 después de que Story 3.1 avanzó implica coordinar una migración de tipo en el frontend — el costo de este cambio depende de qué tan avanzada está esa historia.  
4. Si ya hay `analysis_versions` persistidas en producción con el schema viejo, agregar `not_applicable` no rompe lecturas existentes (es aditivo), pero sí requiere que el merge y el frontend sepan qué hacer con datos históricos que nunca van a tener ese estado.

## Definition of Done

1. Los 6 prompts con categoría confirmada piden exactamente los campos de §5.2.  
2. AD-12 (Pydantic) y el tipo TypeScript de Story 3.1 incluyen `not_applicable` de forma consistente entre sí.  
3. Regla de "no aplica con cita" y regla de "no calcular fechas relativas" implementadas y testeadas.  
4. `tipo` restringido a enum canónico en los prompts de categorías tipo-listado.  
5. Tests verdes cubriendo AC1–AC8.  
6. Mapeo de `restricciones_participacion.txt` y `cronograma_proceso.txt` resuelto con PM y documentado.

## Referencias

- \[Source: prd.md\#5.2\] — diccionario de datos por categoría.  
- \[Source: prd.md\#6.1\] — cuatro estados de un campo, regla de "no aplica".  
- \[Source: prd.md\#6.2\] — confianza como nivel y semántica de acción.  
- \[Source: prd.md\#6.3\] — respaldo verificable obligatorio, formato de citas (incluida regla de tablas).  
- \[Source: 2-5-pipeline-de-extraccion-de-8-categorias-con-ia.md\#AD-12\] — contrato Pydantic actual de `extraction_status`.  
- \[Source: 2-5-pipeline-de-extraccion-de-8-categorias-con-ia.md\#10\] — `merge_node`, detección de conflictos por igualdad exacta de `tipo`.  
- \[Source: 3-1-visualizacion-de-resultados-por-categoria.md\] — tipo TypeScript de `extraction_status` (líneas 146, 456).  
- `backend/analysis/extraction/prompts/garantias.txt` — implementación de referencia ya aplicada.

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

- `backend/analysis/extraction/prompts/garantias.txt` (ya modificado — patrón de referencia)

