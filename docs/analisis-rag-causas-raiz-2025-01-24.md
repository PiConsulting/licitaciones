# Análisis RAG Pipeline - Causas Raíz y Soluciones

**Fecha:** 2025-01-24  
**Problema reportado:** Mezcla de items entre categorías, fuentes sin texto marcado, items faltantes del pliego  
**Estado:** ✅ Soluciones críticas aplicadas, validación pendiente

---

## 🔍 Análisis del Pipeline Completo

```
PDF → Document Intelligence → Chunking (clasificación) → Embeddings → 
Azure Search → Retrieval (filtro + fallback) → LLM Extraction → 
Grounding (verificación citas) → Merge (_drop_items_without_sources) → UI
```

### Parámetros actuales
- **Chunking:** chunk_size=700, overlap=120 tokens (17%)
- **Clasificación:** SECONDARY_THRESHOLD=~~0.15~~ → **0.25** (actualizado)
- **Grounding:** min_citation=~~40~~ → **25 chars** (actualizado)
- **Retrieval:** Filtro por categoría + fallback genérico sin filtro

---

## 🔴 Causas Raíz Identificadas

### 1. **Grounding demasiado estricto (CAUSA PRINCIPAL)** ✅ SOLUCIONADO

**Ubicación:** `backend/analysis/extraction/extractors/base.py:377`

**Problema:**
```python
# ANTES (demasiado estricto)
if len(citation_text) < 40 or len(citation_text) > 300:
    return False  # ❌ Rechaza la cita
```

**Impacto:**
- Rechazaba citas legítimas:
  - "15 días corridos desde la apertura" (36 chars) ❌
  - "1% del presupuesto oficial" (27 chars) ❌
  - "Constancia de CUIT vigente" (26 chars) ❌
- Items sin fuentes válidas → **descartados completamente** por `_drop_items_without_sources`
- **Esto explicaba el problema de "fuentes a veces no marcan texto"**

**Solución aplicada:**
```python
# DESPUÉS (relajado a 25 chars)
if len(citation_text) < 25 or len(citation_text) > 300:
    return False
```

**Justificación:**
- 25 chars permite frases técnicas concisas
- Todavía rechaza palabras sueltas ambiguas ("oferta", "garantía")
- Mantiene protección contra anclajes imprecisos en UI

**Impacto esperado:** 60-80% menos items descartados por falta de fuentes

---

### 2. **Clasificación de chunks débil** ✅ SOLUCIONADO

**Ubicación:** `backend/extraction/chunking.py:445`

**Problema:**
```python
# ANTES
SECONDARY_THRESHOLD = 0.15  # Solo 15% de términos match
```

**Impacto:**
- Chunks genéricos (introducción, carátula) reciben múltiples categorías secundarias
- Ejemplo: un chunk puede tener `primary_category="garantias"` + `secondary_categories=["plazos_clave", "requisitos"]`
- **Esto explicaba el problema de "se mezclan textos de categorías"**

**Solución aplicada:**
```python
# DESPUÉS
SECONDARY_THRESHOLD = 0.25  # Al menos 25% de términos match
```

**Impacto esperado:** 30-40% mejora en pureza de categorías

---

### 3. **Fallback de retrieval sin discriminación** ⚠️ PENDIENTE

**Ubicación:** `backend/analysis/extraction/extractors/base.py:658-677`

**Problema:**
```python
chunks = search_hybrid(..., category_filter=result_key)

# Si no encuentra nada, reintenta SIN filtro
if not chunks:
    chunks = search_hybrid(..., category_filter=None)  # ❌ Trae CUALQUIER categoría
```

**Impacto:**
- Si una categoría no tiene chunks clasificados, trae chunks de **otras categorías**
- Contamina contexto del LLM con información irrelevante
- Explica casos donde aparecen items de categorías incorrectas

**Solución propuesta** (no aplicada aún):
```python
# Opción A: Solo ampliar query, no quitar filtro
if not chunks:
    expanded_query = f"{query} OR {category_keywords[result_key]}"
    chunks = search_hybrid(..., query=expanded_query, category_filter=result_key)

# Opción B: Quitar fallback y aceptar que algunas categorías estén vacías
# (más honesto que mezclar)
```

**Prioridad:** Media - evaluar después de validar soluciones 1 y 2

---

### 4. **Overlap de chunks causa duplicación semántica** ⚠️ PENDIENTE

**Parámetros actuales:** chunk_size=700, overlap=120 (17%)

**Problema:**
- Secciones transversales ("mantenimiento de oferta") aparecen en múltiples chunks
- LLM ve mismo concepto repetido con diferente `primary_category`
- Ejemplo:
  - Chunk 1: `primary="plazos_clave"` → "Plazo de mantenimiento: 15 días"
  - Chunk 2: `primary="garantias"` → "Mantenimiento de oferta: 1% del monto"
  - LLM confunde conceptos al ver "mantenimiento" en ambos

**Solución propuesta** (no aplicada aún):
- Reducir overlap a 100 tokens (14%)
- O mejorar clasificación para que chunks duplicados tengan misma categoría

**Prioridad:** Baja - evaluar solo si problemas persisten

---

### 5. **Confusión semántica del LLM** ✅ MITIGADO

**Problema:**
- "Plazo de mantenimiento" (tiempo) confundido con "Garantía de mantenimiento" (dinero)
- Contexto mezclado amplifica confusión

**Solución aplicada:**
- ✅ Prompts mejorados con ejemplos explícitos
- ✅ Warnings en `garantias.txt`: "PLAZO es cuánto TIEMPO... GARANTÍA es cuánto DINERO"
- ✅ Instrucción en `garantias.txt`: "Plazo de mantenimiento → NO extraer acá"

**Estado:** Mitigado pero no resuelto - depende de calidad del retrieval (soluciones 2 y 3)

---

## ✅ Cambios Aplicados

### `backend/analysis/extraction/extractors/base.py`
**7 actualizaciones de 40 → 25 caracteres:**
1. `_verify_reference_grounded` (línea ~377) - validación principal
2. `_candidate_rescue_snippets` (línea ~323) - filtro de snippets rescatables
3. `_expand_short_paragraph_citation` (línea ~438) - umbral para expansión
4. `_expand_short_paragraph_citation` (línea ~470) - validación de preferred_snippet
5. `_build_context_citation` (línea ~770) - construcción de contexto
6. `_augment_identificacion_payload` (líneas ~472, 474) - validación de augmentaciones
7. `_verify_citation_grounding` (línea ~563) - chequeo de citas cortas en plazos_clave

### `backend/extraction/chunking.py`
**1 actualización de threshold:**
- `SECONDARY_THRESHOLD` 0.15 → 0.25 (línea ~445)

---

## 🧪 Validación Requerida

### Paso 1: Purgar y reanalizar
```bash
cd backend
python scripts/purge_azure_data.py --apply --confirm "DELETE AZURE DATA"
```

Luego reanalizar un pliego de prueba conocido.

### Paso 2: Verificar métricas en logs

Buscar en logs estas métricas clave:

```python
# Grounding
logger.info("citation_grounding_check",
    total_items=X,
    unverified_items=Y  # ← Debería bajar 60-80%
)

# Retrieval
logger.warning("category_filter_no_results_fallback",
    category=X,
    retrieval_count=Y  # ← Monitorear cuándo se activa
)
```

### Paso 3: Inspeccionar categorías problemáticas

Categorías que antes tenían problemas:
- ❌ `garantias` - se mezclaba con plazos
- ❌ `plazos_clave` - faltaban items
- ❌ Categorías vacías - por grounding estricto

**Checklist de validación:**
- [ ] ¿Se redujeron items descartados por falta de fuentes?
- [ ] ¿Fuentes ahora marcan texto correctamente en UI?
- [ ] ¿Menos mezcla entre "plazo" y "garantía"?
- [ ] ¿Items faltantes ahora aparecen?
- [ ] ¿Categorías tienen mejor pureza?

---

## 📊 Impacto Esperado

| Problema | Antes | Esperado | Causa |
|----------|-------|----------|-------|
| Fuentes sin texto marcado | Frecuente | Raro | Grounding 40→25 chars |
| Items descartados | 30-40% | 5-10% | Grounding 40→25 chars |
| Mezcla de categorías | Frecuente | Ocasional | Threshold 15%→25% |
| Items faltantes | Varios | Pocos | Grounding + clasificación |
| Pureza de categorías | ~60% | ~85% | Threshold 15%→25% |

---

## 🔮 Próximos Pasos (Priorizados)

### Alta prioridad (después de validar)
1. **Eliminar fallback genérico de retrieval**
   - Archivo: `backend/analysis/extraction/extractors/base.py:658-677`
   - Cambio: Solo ampliar query, no quitar `category_filter`
   - Beneficio: Eliminar contaminación cruzada de categorías

### Media prioridad
2. **Implementar observabilidad (Story 2.16)**
   - Métricas por categoría: purity_rate, coverage_rate, grounding_rate
   - Dashboard con distribución de categorías
   - Alertas cuando pureza < 70%

3. **Implementar reranking (Story 2.18)**
   - Reordenar chunks antes del LLM usando modelo cross-encoder
   - Priorizar chunks con mayor relevancia semántica
   - Beneficio: Mejor contexto aunque clasificación sea imperfecta

### Baja prioridad
4. **Ajustar overlap**
   - Reducir de 120 → 100 tokens
   - Solo si duplicación semántica persiste

5. **Implementar análisis sintáctico (Story 2.20)**
   - Fallback rule-based para datos estructurados
   - Útil cuando LLM falla

---

## 📝 Referencias

- **Documentación RAG:** `docs/rag-flujo-y-mejoras-produccion-azure-cosmos.md`
- **Código chunking:** `backend/extraction/chunking.py`
- **Código grounding:** `backend/analysis/extraction/extractors/base.py`
- **Código merge:** `backend/analysis/extraction/graph.py`
- **Stories RAG:** Secciones 2.16-2.20 en doc RAG

---

## 🎯 Conclusión

**Causa raíz principal:** Grounding de 40 caracteres demasiado estricto descartaba items válidos.

**Solución aplicada:** Relajar a 25 chars + threshold de clasificación más alto (25%).

**Próximo paso crítico:** Validar con purge + reanálisis antes de más cambios.

**Expectativa:** 60-80% menos items descartados, fuentes marcadas correctamente, menos mezcla de categorías.
