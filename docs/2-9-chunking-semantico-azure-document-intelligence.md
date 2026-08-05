---

## story\_id: "2.9" story\_key: "2-9-chunking-semantico-azure-document-intelligence" epic: 2 title: "Chunking semantico basado en la estructura nativa de Azure Document Intelligence (roles y tablas)" status: "draft" created: "2026-08-05" epic\_title: "Analisis de Pliegos (Subida \+ Extraccion \+ Progreso)"

# Story 2.9: Chunking semantico basado en la estructura nativa de Azure Document Intelligence (roles y tablas)

## User Story

Como equipo de ingenieria de CedIA, quiero que el chunking use la estructura nativa que devuelve Azure Document Intelligence (roles de parrafo como title/sectionHeading, y tablas) para la ruta que realmente corre en produccion, para que ningun chunk mezcle contenido de dos secciones distintas, ninguna tabla se rompa a mitad de fila, y las citas de campos que viven en tablas sigan siendo verificables.

## Por que esta historia, distinta de la 2.8

La Story 2.8 ya resuelve chunking jerarquico a partir de headings Markdown (`#`, `##`, `###`) que produce **MarkItDown**. Pero segun **FR-3.1** y **§4.1** del PRD, la ruta de produccion para **todo** documento — nativo digital y escaneado — es **Azure AI Document Intelligence con modelo prebuilt-layout**, no MarkItDown (MarkItDown queda como adaptador de paridad local/desarrollo, segun el propio Contexto Actual del Codigo de 2.8: "modo MarkItDown ... por limitacion de paginacion").

Document Intelligence no devuelve Markdown: devuelve `paragraphs`, cada uno con un `role` (`title`, `sectionHeading`, `pageHeader`, `footnote`, `pageFooter`, contenido normal), y `tables` con estructura real de filas/columnas y `kind` por celda (`columnHeader`/`content`). El adaptador actual (`AzureDocumentIntelligenceAdapter.extract_text`) sólo concatena `page.lines` y descarta esa estructura — así que, aunque 2.8 se implemente, la ruta que de verdad corre en producción sigue sin `section_path`/`section_level` confiables, y las tablas llegan a chunking como texto plano sin estructura. Eso incumple dos requisitos explícitos del PRD:

- **FR-3.1**, criterio de aceptación: "Dado un PDF con tablas, cuando el sistema lo procesa con prebuilt-layout, entonces conserva la estructura tabular."  
- **§6.3** (Respaldo Verificable Obligatorio): "Si la información está en una tabla, la cita incluye el encabezado de la columna y la fila relevante."

Esta historia no reemplaza a 2.8: la complementa, generalizando su mismo contrato de salida (`section_key`, `section_path`, `section_level`) para que también se produzca correctamente desde la ruta Azure Document Intelligence, y agrega el manejo de tablas que 2.8 no cubre (2.8 está scopeado a headings Markdown de texto, no a tablas).

## Acceptance Criteria

### AC1: Extracción de roles de párrafo desde Document Intelligence

**Given** un resultado de `client.begin_analyze_document(model_id="prebuilt-layout")` **When** `AzureDocumentIntelligenceAdapter.extract_text` procesa el resultado **Then** itera `result.paragraphs` (no sólo `page.lines`) y clasifica cada uno por su `role`: `title`/`sectionHeading` alimentan la jerarquía, `pageHeader`/`pageFooter`/`footnote` se excluyen del contenido de negocio, el resto se trata como párrafo normal.

### AC2: `section_path`/`section_level` también desde la ruta Azure DI

**Given** párrafos con roles de heading intercalados con contenido normal, en orden de aparición **When** se recorre el documento **Then** se construye el mismo shape que 2.8 introdujo (`section_path`, `section_level`) acumulando el heading vigente — un único formato intermedio de "documento con jerarquía" alimenta a `create_chunks`, sin importar si vino de MarkItDown (2.8) o de Document Intelligence (esta historia).

### AC3: Tablas como unidad citable, no como texto plano

**Given** `result.tables` con celdas (`row_index`, `column_index`, `content`, `kind`) **When** se arma el contenido para chunking **Then** cada tabla se serializa como un bloque propio que conserva el encabezado de columna asociado a cada fila (no se disuelve en texto libre), y ese bloque no se corta con overlap de tokens a mitad de fila — una tabla grande puede dividirse por filas completas, nunca a mitad de una celda.

### AC4: Citas verificables de datos en tablas

**Given** un campo cuyo valor vive en una tabla (ej. ponderaciones en "Criterios de evaluación", montos en un cuadro de "Garantías") **When** el extractor arma `source_references` **Then** la cita incluye el encabezado de columna relevante junto con el contenido de la fila, tal como exige §6.3: "la cita incluye el encabezado de la columna y la fila relevante."

### AC5: Contrato de chunk unificado entre 2.8 y esta historia

**Given** el shape de chunk que define 2.8 (`document_id`, `chunk_index`, `content`, `token_count`, `section_key`, `section_path`, `section_level`) **When** se genera un chunk desde la ruta Azure Document Intelligence **Then** el shape es idéntico al de la ruta MarkItDown; `create_chunks` no necesita saber de qué adaptador vino cada bloque, sólo consume una lista de bloques jerárquicos con contenido (texto o tabla ya serializada a texto citable).

### AC6: Fallback legal se preserva

**Given** un documento donde Document Intelligence no asigna roles útiles a ningún párrafo (pliego escaneado con OCR de baja calidad) **When** no hay `title`/`sectionHeading` detectables **Then** se aplica el mismo fallback legal (capítulo/artículo/anexo/inciso) que 2.8 ya define, sin excepciones — ambas rutas comparten el mismo fallback, no se duplica la lógica.

### AC7: Observabilidad

**Given** ejecución con logging estructurado y `correlation_id` **When** corre la extracción de estructura desde Document Intelligence **Then** se registran métricas por documento: párrafos por `role`, cantidad y tamaño de tablas detectadas, y cuántas secciones se resolvieron por `role` vs por fallback legal.

## Scope Técnico

- `backend/extraction/document_intelligence.py` — `AzureDocumentIntelligenceAdapter.extract_text`: leer `paragraphs` (con `role`) y `tables` en vez de sólo `page.lines`.  
- `backend/extraction/chunking.py` — generalizar el parser jerárquico de 2.8 para aceptar bloques de origen Document Intelligence además de Markdown, convergiendo en un único formato intermedio.  
- Serializador de tablas a texto citable (encabezado \+ fila), reutilizable entre chunking y `_format_chunks`.  
- `backend/analysis/extraction/extractors/base.py` — `_format_chunks` debe poder mostrar contexto de tabla de forma distinta al contexto de párrafo (para que el LLM entienda que está leyendo una fila de una tabla, no una oración suelta).

## Contexto Actual del Código (Debe Preservarse)

- `AzureDocumentIntelligenceAdapter.extract_text` hoy sólo usa `page.lines`, descartando `paragraphs` y `tables` del resultado de `prebuilt-layout`.  
- El shape de chunk que define/definirá 2.8 (`section_key`, `section_path`, `section_level`) debe mantenerse compatible — esta historia extiende, no reemplaza, ese contrato.  
- `search_hybrid` y `ai_search.py` deben seguir filtrando por `analysis_id`/`section_key` sin romperse por los campos nuevos.

## Tareas / Subtareas

- [ ] T1: Leer `paragraphs` con `role` desde Document Intelligence (AC1)  
        
      - [ ] Confirmar en la versión del SDK (`azure-ai-documentintelligence`) usada en el proyecto que `paragraphs[].role` está disponible para `prebuilt-layout` (puede variar entre preview/GA).  
      - [ ] Clasificar roles y descartar `pageHeader`/`pageFooter`/`footnote` del contenido de negocio.

      

- [ ] T2: Construir `section_path`/`section_level` desde roles de heading (AC2, AC5)  
        
      - [ ] Reusar/generalizar el acumulador de jerarquía que 2.8 implementa para Markdown.  
      - [ ] Validar que el shape de salida es idéntico entre ambas rutas con un mismo test de contrato (mismo esquema de dict, independientemente del adaptador de origen).

      

- [ ] T3: Serializar tablas como bloque citable (AC3, AC4)  
        
      - [ ] Mapear `tables[].cells` a texto con encabezado de columna \+ fila.  
      - [ ] Asegurar que una tabla grande se divide sólo entre filas completas, nunca a mitad de celda.  
      - [ ] Propagar la referencia de tabla (identificador de tabla \+ fila) hasta `source_references`.

      

- [ ] T4: Fallback legal compartido (AC6)  
        
      - [ ] Verificar que el mismo módulo de fallback legal de 2.8 se invoca desde ambas rutas sin duplicar la regex ni el criterio de "no hay heading útil".

      

- [ ] T5: Observabilidad y tests (AC7)  
        
      - [ ] Logs de conteo de roles/tablas/fallback por documento.  
      - [ ] Tests con al menos un pliego de fixture con tablas reales (ej. cuadro de criterios de evaluación) verificando que ninguna fila queda partida y que la cita incluye encabezado.

## Dev Notes

### Requerimientos de Arquitectura y Cumplimiento

- Depende del contrato que fije Story 2.8: si 2.8 no está implementada aún, coordinar el shape de salida (`section_path`, `section_level`) para no mantener dos formatos distintos en paralelo.  
- Respeta FR-3.1 (conservar estructura tabular) y §6.3 (cita de tabla con encabezado \+ fila) del PRD — ambos son criterios de aceptación explícitos, no una mejora opcional.  
- AD-4 (índice compartido de Azure AI Search): los campos nuevos (`section_path`, `section_level`, referencia de tabla) deben indexarse sin romper el filtro por `analysis_id`/`section_key`.

### Guardrails de Implementación (Obligatorios)

- No mantener dos parsers jerárquicos independientes (uno para MarkItDown, otro para Document Intelligence) — deben converger en el mismo formato intermedio antes de `create_chunks`.  
- No disolver tablas en texto libre: una tabla es una unidad estructural propia, no un párrafo más.  
- No romper `section_key`, del que dependen los filtros existentes de `search_hybrid`.

### Inteligencia de Historia Previa y Commits

- Story 2.4/2.5 establecieron el pipeline de extracción e indexación.  
- Story 2.8 resuelve el caso Markdown/MarkItDown; esta historia resuelve el caso Azure Document Intelligence, que es el que corre en producción según FR-3.1.

### Información Técnica Actualizada

- Azure AI Document Intelligence, modelo `prebuilt-layout`: expone `paragraphs[].role` y `tables[].cells[].kind` (`columnHeader`/`content`) en el SDK Python `azure-ai-documentintelligence`. Confirmar la versión exacta usada en el proyecto antes de implementar — el nombre y disponibilidad de estos campos varió entre versiones preview y GA del servicio.

## Riesgos / Dudas a Validar Antes de Estimar

1. Confirmar que la versión del SDK instalada expone `role` en `paragraphs` para el modelo `prebuilt-layout` tal como se espera — validar contra un pliego real antes de estimar.  
2. Serializar tablas cambia el formato de texto que llega al LLM; puede requerir ajuste de prompts (coordinar con la historia de prompts, 2.10).  
3. Pliegos escaneados con OCR de baja calidad pueden no traer roles confiables — medir tasa real de fallback en el corpus disponible.  
4. Definir si el "identificador de tabla" que se propaga a `source_references` necesita cambios en el visor PDF (Story 3.2) para resaltar una fila/celda en vez de sólo un fragmento de texto.

## Definition of Done

1. `AzureDocumentIntelligenceAdapter.extract_text` expone roles y tablas estructuradas.  
2. `create_chunks` produce el mismo shape (`section_key`, `section_path`, `section_level`) para ambas rutas de ingesta (MarkItDown y Document Intelligence).  
3. Tablas preservadas como unidad citable, con encabezado de columna en la cita.  
4. Tests de regresión sobre corpus con tablas reales, sin filas partidas.  
5. Logs estructurados permiten auditar roles/tablas/fallback detectados por documento.

## Referencias

- \[Source: prd.md\#FR-3.1\] — "conserva la estructura tabular" como criterio de aceptación.  
- \[Source: prd.md\#6.3\] — formato de citas, incluida la regla de tablas.  
- \[Source: prd.md\#4.1\] — Azure AI Document Intelligence, prebuilt-layout para nativos y OCR.  
- Story 2.8 (`2-8-chunking-jerarquico-basado-en-markdown-markitdown.md`) — contrato de `section_path`/`section_level` a generalizar.  
- `backend/extraction/document_intelligence.py`, `backend/extraction/chunking.py`, `backend/analysis/extraction/extractors/base.py`.

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

