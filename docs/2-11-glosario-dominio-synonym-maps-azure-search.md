---

## story\_id: "2.11" story\_key: "2-11-glosario-dominio-synonym-maps-azure-search" epic: 2 title: "Glosario de vocabulario del dominio con Synonym Maps de Azure AI Search para recuperacion y comparacion no literal" status: "draft" created: "2026-08-05" epic\_title: "Analisis de Pliegos (Subida \+ Extraccion \+ Progreso)"

# Story 2.11: Glosario de vocabulario del dominio con Synonym Maps de Azure AI Search para recuperación y comparación no literal

## User Story

Como Ejecutivo Comercial que confía en que el análisis encontró todo lo relevante, quiero que cada nodo de extracción encuentre y reconozca la información aunque el pliego use un término distinto al esperado, para que un campo no quede "No encontrado" sólo porque el pliego lo nombró distinto (ej. "boleta de garantía" en vez de "garantía", "prórroga" en vez de "extensión de plazo").

## Por qué esta historia (dos problemas distintos, no uno)

Con integración Azure ya confirmada en todo el pipeline (Azure AI Document Intelligence, Azure OpenAI, Azure AI Search — §4.1 y AD-4 del PRD/Story 2.5), esta historia tiene dos partes que conviene distinguir porque se resuelven con mecanismos distintos:

**Problema 1 — Recuperación.** Cada extractor (código completo en Story 2.5 §7–8, idéntico al que corre hoy en el repo) usa una **única query de texto fija y hardcodeada en Python**:

```py
# garantias.py
query = "garantía oferta cumplimiento anticipo monto caución seguro"
# plazos.py
query = "plazos fecha presentación ofertas apertura adjudicación vigencia"
```

Esa query alimenta `search_hybrid` contra el índice de Azure AI Search (AD-4). Si el pliego llama a la garantía "boleta de garantía de mantenimiento de oferta" o "fianza de seriedad de oferta", la recuperación puede no traer el chunk correcto entre los `top_k=10`.

**Problema 2 — Comparación en el merge.** Independientemente de la búsqueda, `merge_node` (Story 2.5 §10) detecta conflictos comparando **por igualdad exacta de string** sobre el campo `tipo`:

```py
garantias_by_tipo = {}
for garantia in extracted_data["garantias"]:
    tipo = garantia.get("tipo")
    if tipo in garantias_by_tipo:
        ...  # conflicto
    else:
        garantias_by_tipo[tipo] = garantia
```

Si el LLM devuelve `tipo="garantía de oferta"` para un documento y `tipo="garantía de mantenimiento de oferta"` para otro — ambos correctos, sólo con vocabulario distinto — el merge los trata como dos garantías diferentes en vez de detectar que son la misma y, potencialmente, un conflicto real. La propia Story 2.5 ya deja esto anotado como pendiente: *"TODO: Detección de conflictos semánticos (equivalencia \>85%) — Requiere embeddings y cosine similarity"* (§10). Esta historia no resuelve ese TODO con embeddings; lo resuelve más barato, restringiendo `tipo` a un enum canónico en el prompt (ver Story 2.10, AC8) — el glosario de esta historia es lo que permite que ese enum tenga cobertura real del vocabulario que aparece en pliegos reales.

## Decisión técnica: Synonym Maps nativos de Azure AI Search, no expansión de query en Python

Azure AI Search tiene un mecanismo nativo para exactamente el Problema 1: **Synonym Maps** (formato Apache Solr, hasta 20.000 reglas por mapa fuera del tier gratuito, expansión en tiempo de consulta **sin necesidad de reindexar**). Dado que "ahora todo es integración Azure", conviene usar este mecanismo en vez de reimplementar expansión de queries a mano en cada extractor — es menos código, es la forma soportada por el proveedor, y no requiere tocar los 8 extractores cada vez que se agrega un sinónimo nuevo.

El SDK Python (`azure.search.documents.indexes.models.SynonymMap`) permite crear/actualizar el mapa vía `SearchIndexClient`, y se asocia a un campo del índice con la propiedad `synonymMaps`. \[Source: learn.microsoft.com/azure/search/search-synonyms\]

En el modo local de desarrollo (ChromaDB, sin Azure AI Search), este mecanismo no existe — para ese modo se necesita una expansión de query equivalente en código Python, documentada como solución **sólo para local**, para no mantener dos implementaciones de lo mismo en producción.

## Acceptance Criteria

### AC1: Glosario de dominio versionado como fuente única de verdad

**Given** el vocabulario real observado en pliegos (garantías, plazos, causales, etc.) **When** se documenta el glosario **Then** existe un archivo de datos versionado en el repo (no hardcodeado en Python), con una entrada por concepto canónico y sus variantes conocidas, del cual se derivan tanto las reglas del Synonym Map de Azure AI Search como el bloque de vocabulario equivalente que Story 2.10 inserta en cada prompt — una sola fuente, no dos mantenidas a mano por separado.

### AC2: Synonym Map creado y asociado al campo de búsqueda

**Given** el glosario del AC1, convertido a reglas formato Solr (equivalencia o mapeo explícito, frases multi-palabra entre comillas) **When** se provisiona el índice de Azure AI Search **Then** existe un Synonym Map por dominio (o uno único con todas las categorías) creado vía `SearchIndexClient`, asociado al campo `content` (o el campo relevante) mediante `synonymMaps`, y la expansión ocurre en tiempo de consulta sin reindexar la colección existente.

### AC3: Extractores dejan de tener query hardcodeada

**Given** cada extractor (`garantias.py`, `plazos.py`, etc.) **When** arma su query para `search_hybrid` **Then** la lee de una lista de términos base por categoría definida en el glosario, no de un string fijo embebido en el código Python — la expansión de sinónimos la resuelve el Synonym Map del lado de Azure AI Search, no el extractor.

### AC4: Paridad funcional en modo local (ChromaDB)

**Given** que ChromaDB no tiene Synonym Maps nativos **When** el pipeline corre en modo local/desarrollo **Then** se aplica una expansión de query equivalente en código (multi-término a partir del mismo glosario del AC1), documentada explícitamente como solución exclusiva del modo local, sin duplicar esa lógica en el camino de producción con Azure AI Search.

### AC5: `tipo` como enum canónico alineado al glosario

**Given** el criterio de identidad usado por `merge_node` para detectar el "mismo ítem" **When** el prompt de cada categoría tipo-listado define su enum de `tipo` (Story 2.10, AC8) **Then** los valores del enum son exactamente los conceptos canónicos del glosario de esta historia — el glosario y el enum de `tipo` no pueden divergir, o el merge vuelve a fallar por vocabulario no cubierto.

### AC6: Tests de recuperación y de comparación con sinónimo no cubierto

**Given** un pliego de fixture que usa un sinónimo no incluido en la query original de hoy (ej. "boleta de garantía" en vez de "garantía") **When** corre el extractor correspondiente **Then** el chunk relevante aparece entre los `top_k` resultados y el extractor devuelve `extraction_status="success"`; además, un segundo pliego de fixture con el mismo concepto nombrado distinto no genera una entrada duplicada en el listado fusionado del merge.

### AC7: Trazabilidad del glosario

**Given** cada entrada del glosario **When** se documenta **Then** incluye, cuando sea posible, de qué pliego/fuente se tomó la variante — para poder auditar por qué el sistema reconoce ese término como sinónimo.

## Ejemplos de variantes a cubrir (semilla del glosario)

| Categoría | Término canónico | Variantes observadas |
| :---- | :---- | :---- |
| Garantías | mantenimiento de oferta | garantía de oferta, garantía de seriedad de oferta, caución de oferta, fianza de oferta, boleta de garantía de oferta |
| Garantías | cumplimiento de contrato | garantía de fiel cumplimiento, garantía de ejecución de contrato, fianza de cumplimiento |
| Plazos | presentación de ofertas | fecha límite de presentación, cierre de recepción de ofertas |
| Plazos | mantenimiento de oferta (plazo) | prórroga de oferta, extensión de vigencia de oferta |
| Causales de rechazo | causal de rechazo | motivo de descalificación, causa de exclusión, causal de inadmisibilidad |

*(Punto de partida ilustrativo — Task 1.2 debe ampliarlo contra pliegos reales del proyecto.)*

## Tareas / Subtareas

- [ ] T1: Construir el glosario de dominio (AC1, AC7)  
        
      - [ ] 1.1 Definir el esquema de datos (ej. YAML por categoría: `canonico`, `variantes: []`, `fuente` opcional).  
      - [ ] 1.2 Poblar la primera versión priorizando las tres categorías críticas (garantías, plazos clave, causales de rechazo — §5.3 del PRD), revisando el corpus de pliegos disponible.

      

- [ ] T2: Provisionar Synonym Map en Azure AI Search (AC2)  
        
      - [ ] 2.1 Convertir el glosario a reglas formato Solr.  
      - [ ] 2.2 Script/migración de infraestructura para crear/actualizar el Synonym Map vía `SearchIndexClient` (`azure-search-documents`).  
      - [ ] 2.3 Asociar el Synonym Map al campo `content` del índice existente (AD-4) sin reindexar.  
      - [ ] 2.4 Confirmar el tier del servicio de Azure AI Search contratado (free vs standard) para dimensionar el volumen de reglas (5.000 en free, 20.000 en otros tiers).

      

- [ ] T3: Extractores leen del glosario, no de query hardcodeada (AC3)  
        
      - [ ] 3.1 Migrar los 8 extractores para leer su lista de términos base del glosario.  
      - [ ] 3.2 Confirmar que la expansión real ocurre en Azure AI Search (Synonym Map), no en el extractor.

      

- [ ] T4: Paridad en modo local (AC4)  
        
      - [ ] 4.1 Implementar expansión de query equivalente para ChromaDB a partir del mismo glosario.  
      - [ ] 4.2 Documentar explícitamente que esa expansión es sólo para desarrollo local.

      

- [ ] T5: Enum de `tipo` alineado (AC5) — coordinar con Story 2.10  
        
      - [ ] 5.1 Generar el enum de `tipo` de cada prompt a partir de los términos canónicos del glosario (no mantenerlo a mano por separado).

      

- [ ] T6: Tests (AC6)  
        
      - [ ] 6.1 Un caso de recuperación por categoría con sinónimo no cubierto por la query original.  
      - [ ] 6.2 Un caso de merge con el mismo concepto nombrado distinto en dos documentos, verificando que no se duplica en el listado fusionado.  
      - [ ] 6.3 Caso negativo: un término genuinamente ausente del pliego sigue devolviendo `not_found` (para no perder precisión al expandir la búsqueda).

## Dev Notes

### Requerimientos de Arquitectura y Cumplimiento

- Respeta AD-4 (índice compartido de Azure AI Search, búsqueda híbrida filtrada por `analysis_id`) — el Synonym Map es un agregado sobre ese índice existente, no un índice nuevo.  
- "El cambio de local a Azure ocurre por configuración, sin cambiar la lógica de extractores" (Story 2.5, AD-4) — esta historia debe preservar esa propiedad: los extractores no deberían necesitar saber si la expansión de sinónimos viene de un Synonym Map de Azure o de la expansión local en código.  
- Depende de Story 2.10 (AC8) para el enum canónico de `tipo` en los prompts — ambas historias comparten el mismo glosario como fuente.

### Guardrails de Implementación (Obligatorios)

- No reimplementar expansión de sinónimos en Python para el camino de producción — usar el mecanismo nativo de Azure AI Search.  
- No mantener el glosario en dos lugares (un YAML y, aparte, un enum hardcodeado en cada prompt) — el enum de `tipo` se genera desde el glosario, no al revés.  
- No asumir que el Synonym Map resuelve la comparación en `merge_node` — el Synonym Map sólo afecta recuperación (qué chunks aparecen en el `top_k`); la comparación de "mismo ítem" sigue dependiendo del enum canónico de `tipo` que define Story 2.10.

### Inteligencia de Historia Previa y Commits

- Story 2.5 dejó documentado el TODO de conflictos semánticos (§10) sin resolver — esta historia lo resuelve con un enum canónico más barato que embeddings \+ cosine similarity, no con el mecanismo que el TODO originalmente sugería.  
- AD-4 (Story 2.5) ya establece el índice de Azure AI Search compartido sobre el que se agrega el Synonym Map.

### Información Técnica Actualizada (Web)

- Azure AI Search Synonym Maps: API version 2026-04-01 vigente al momento de esta historia, formato Solr con reglas de equivalencia y de mapeo explícito, frases multi-palabra entre comillas dobles, hasta 5.000 reglas por mapa en tier gratuito y 20.000 en otros tiers. La expansión aplica en tiempo de consulta sin necesidad de reindexar. SDK disponible en Python (`azure.search.documents.indexes.models.SynonymMap`), .NET, Java, y como interfaz en JavaScript. \[Source: https://learn.microsoft.com/en-us/azure/search/search-synonyms\]

## Riesgos / Dudas a Validar Antes de Estimar

1. Confirmar el tier contratado de Azure AI Search — el límite de reglas por Synonym Map (5.000 vs 20.000) condiciona qué tan granular puede ser el glosario.  
2. Validar con casos reales que las reglas multi-palabra (ej. "boleta de garantía de mantenimiento de oferta" completo, no sólo términos sueltos) funcionan como se espera en formato Solr — requiere prueba contra el índice real, no sólo lectura de documentación.  
3. Confirmar si el Synonym Map debe ser uno solo para todo el dominio o uno por categoría — afecta cómo se filtra la expansión cuando dos categorías comparten una palabra con sentido distinto.  
4. El AC5 (enum de `tipo` alineado al glosario) depende de que Story 2.10 avance en paralelo o antes — evaluar si conviene fusionar la implementación de ambas historias en un mismo ciclo.

## Definition of Done

1. Glosario de dominio versionado en el repo, con al menos las tres categorías críticas cubiertas.  
2. Synonym Map creado en Azure AI Search y asociado al índice existente sin reindexar.  
3. Los 8 extractores leen su query base del glosario, no de un string hardcodeado.  
4. Paridad documentada y funcional en modo local (ChromaDB).  
5. Enum de `tipo` en los prompts generado desde el mismo glosario (coordinado con Story 2.10).  
6. Tests verdes de recuperación con sinónimo no cubierto y de no-duplicación en merge.

## Referencias

- \[Source: prd.md\#4.1, AD-4\] — Azure AI Search, índice compartido, búsqueda híbrida.  
- \[Source: 2-5-pipeline-de-extraccion-de-8-categorias-con-ia.md\#7-8\] — queries hardcodeadas en `plazos.py` y `garantias.py` (código completo).  
- \[Source: 2-5-pipeline-de-extraccion-de-8-categorias-con-ia.md\#10\] — `merge_node`, comparación exacta de `tipo`, TODO de conflictos semánticos.  
- \[Source: https://learn.microsoft.com/en-us/azure/search/search-synonyms\] — Synonym Maps, formato Solr, límites por tier, SDK Python.  
- Story 2.10 (`2-10-prompts-alineados-diccionario-y-estados.md`) — AC8, enum canónico de `tipo`.  
- `backend/analysis/extraction/extractors/garantias.py`, `backend/shared/ports/azure_search.py`.

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

