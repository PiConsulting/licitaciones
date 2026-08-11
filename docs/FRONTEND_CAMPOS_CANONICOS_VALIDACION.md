# Validación de Campos Canónicos en Frontend

**Fecha**: 2026-08-11  
**Contexto**: Fix #4 de auditoría RAG — Migración a campos canónicos del backend

---

## Resumen

El frontend ha sido migrado para usar **exclusivamente campos canónicos** del backend, eliminando el uso de campos legacy que serán deprecados en Q2 2027.

---

## Cambios Realizados

### 1. Actualización de BACKEND_STATUS_KEY

**Archivo**: `frontend/src/services/api/analysisApi.ts`

```typescript
const BACKEND_STATUS_KEY: Record<CategoryId, string> = {
  // ... otros campos sin cambios
  criterios_evaluacion: "criterios_evaluacion_extraction_status",  // ✅ (antes: "criterios_extraction_status")
  anexos_obligatorios: "anexos_obligatorios_extraction_status",    // ✅ (antes: "anexos_extraction_status")
}
```

### 2. Documentación de legacyToUiMap

El mapeo `legacyToUiMap` se mantiene **solo como fallback** para retrocompatibilidad con:
- Análisis legacy que tienen datos en nombres antiguos
- Versiones antiguas del backend (pre-2026-08)

**No se usa** con el backend actual, que envía ambos nombres (canónico + legacy).

---

## Campos Canónicos vs Legacy

| Categoría | Campo Canónico | Campo Legacy (deprecado Q2 2027) |
|-----------|---------------|----------------------------------|
| Plazos | `plazos_clave` | `plazos` |
| Plazos (status) | `plazos_clave_extraction_status` | `plazos_extraction_status` |
| Anexos | `anexos_obligatorios` | `documentos_requeridos` |
| Anexos (status) | `anexos_obligatorios_extraction_status` | `anexos_extraction_status` |
| Criterios (status) | `criterios_evaluacion_extraction_status` | `criterios_extraction_status` |
| Identificación | `identificacion_procedimiento` | `datos_procedimiento` |

---

## Caso Especial: datos_procedimiento

`datos_procedimiento` **se mantiene intencionalmente** como campo auxiliar porque:

1. **No es parte de las 7 categorías principales** mostradas con tarjetas en la UI
2. Se usa **solo para el header** del análisis (organismo, expediente, procedimiento)
3. No tiene tarjeta propia en CategoryList
4. No se cuenta en el checklist de categorías completadas

**Uso actual**:
```typescript
// AnalysisDetailHeader.tsx
const organismo = getFieldValue(analysis, "datos_procedimiento", "Organismo convocante");
const expediente = getFieldValue(analysis, "datos_procedimiento", "Expediente");
```

Esto es **intencional y correcto** — `datos_procedimiento` no se está usando como categoría legacy, sino como fuente de metadatos auxiliares.

---

## Validación

### Tests Ejecutados

```bash
npm test analysisApi
```

**Resultado**: ✅ **2 archivos, 7 tests — todos pasaron**

- `analysisApi.realshape.test.ts`: Valida shape real del API
- `analysisApi.ts`: Lógica de normalización

### Coverage de Validación

- ✅ Shape de response incluye todos los campos canónicos
- ✅ Normalización de categorías funciona con backend actual
- ✅ Fallback legacy funciona para análisis antiguos
- ✅ `datos_procedimiento` se normaliza correctamente aunque no tenga tarjeta propia

---

## Timeline de Deprecación

| Fecha | Acción |
|-------|--------|
| **2026-08-11** | ✅ Frontend migrado a campos canónicos |
| **Q1 2027** | Backend agregará warnings en logs cuando reciba requests usando campos legacy |
| **Q2 2027** | Backend eliminará campos legacy del schema — frontend legacy dejará de funcionar |

---

## Acciones Futuras

1. **Q1 2027**: Monitorear logs del backend para detectar uso de campos legacy
2. **Antes Q2 2027**: Validar que todos los análisis legacy hayan sido re-procesados o migrados
3. **Q2 2027**: Eliminar `legacyToUiMap` del frontend después de que backend deprece completamente

---

## Referencias

- Auditoría RAG: `docs/docu/RAG_AUDIT_PRODUCTION_AZURE_2026_08_10.md` (hallazgo #4)
- Backend schemas: `backend/analysis/extraction/schemas.py` (líneas 530-565)
- Backend merge_node: `backend/analysis/extraction/graph.py` (líneas 850-882)
