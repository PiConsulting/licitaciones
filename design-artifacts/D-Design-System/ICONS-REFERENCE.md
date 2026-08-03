# Referencia Rápida de Iconos — CedIA

**Librería:** [Lucide React](https://lucide.dev)  
**Package:** `lucide-react` v0.460.0+  
**Documentación completa:** Ver [DESIGN.md](./DESIGN.md#icons) y [00-UX-SPECIFICATIONS.md](./00-UX-SPECIFICATIONS.md) §6.5

---

## Instalación

```bash
npm install lucide-react
```

## Uso Básico

```tsx
import { FileText, AlertTriangle, CheckCircle } from 'lucide-react'

// Tamaño por defecto (20px)
<FileText />

// Tamaño personalizado
<AlertTriangle size={16} />

// Con clases Tailwind
<CheckCircle size={24} className="text-success" />

// Loading animado
<Loader2 size={20} className="animate-spin text-primary" />
```

---

## Tamaños Estándar

| Token | Px | Uso |
|-------|----|----|
| **sm** | 16px | Inline con badges, texto pequeño |
| **md** | 20px | **Default** — Botones, inputs, navegación |
| **lg** | 24px | Headers, títulos de sección |
| **xl** | 32px | Ilustraciones, estados vacíos |

---

## Mapeo Completo

### 🔧 Iconos del Sistema

| Concepto | Icono Lucide | Contexto de uso |
|----------|--------------|-----------------|
| Documento/Archivo | `FileText` | Pliegos, archivos PDF, lista de documentos |
| Fecha | `Calendar` | Timestamps, fechas de análisis, plazos |
| Progreso/Revisión | `ClipboardCheck` | Categorías revisadas, checklist |
| Buscar | `Search` | Input de búsqueda, buscadores |
| Menú principal | `List` | Icono de navegación principal |
| Más opciones (⋮) | `MoreVertical` | Menús contextuales, acciones secundarias |
| Expandir ▾ | `ChevronDown` | Dropdowns, colapsables (cerrados) |
| Colapsar ▴ | `ChevronUp` | Colapsables (abiertos) |
| Volver | `ArrowLeft` | Navegación atrás, breadcrumbs |
| Siguiente | `ArrowRight` | Avanzar, wizard steps |
| Re-analizar | `RefreshCw` | Acción de re-análisis |
| Subir archivos | `Upload` | Drag & drop zone, file picker |
| Descargar | `Download` | Exportar (fuera de MVP) |
| Eliminar | `Trash2` | Eliminar análisis, archivos |
| Editar | `Edit` | Editar campo, corrección manual |
| Ver | `Eye` | Ver fuente, preview |
| Agregar | `Plus` | Crear nuevo, agregar campo |
| Cerrar | `X` | Cerrar modal, eliminar tag |
| Usuario | `User` | Perfil, usuario que creó |
| Configuración | `Settings` | Ajustes (fuera de MVP) |

---

### ✅ Iconos de Estado (Análisis)

| Estado | Icono Lucide | Color Tailwind | Uso |
|--------|--------------|----------------|-----|
| **En cola** | `Clock` | `text-gray-600` | Badge: análisis esperando procesamiento |
| **Analizando** | `Loader2` | `text-primary animate-spin` | Badge: procesamiento en curso |
| **Analizado** | `AlertTriangle` | `text-warning` | Badge: completado pero sin validar |
| **Validado** | `CheckCircle` | `text-success` | Badge: revisado y aprobado |
| **Error** | `XCircle` | `text-error` | Badge: falló el procesamiento |
| **Cancelado** | `X` | `text-gray-500` | Badge: análisis cancelado |

---

### 🎯 Iconos de Confianza (Campos Extraídos)

| Nivel | Icono Lucide | Color Tailwind | Descripción |
|-------|--------------|----------------|-------------|
| **Alta** | `CheckCircle` | `text-success` | ✓ Extracción con alta certeza |
| **Media** | `Info` | `text-info` | ℹ️ Requiere verificación |
| **Baja** | `AlertTriangle` | `text-critical` | ⚠️ Confianza baja, revisar fuente |
| **En Conflicto** | `XCircle` | `text-error` | ❌ Valores contradictorios detectados |
| **No Encontrado** | `AlertTriangle` | `text-warning` | ⚠️ Dato no localizado en documentos |
| **No Aplica** | `Info` | `text-info` | ℹ️ Campo no requerido para este pliego |

---

### 🧭 Iconos de Navegación

| Elemento | Icono Lucide | Ubicación |
|----------|--------------|-----------|
| Dashboard | `LayoutDashboard` | Sidebar navegación |
| Historial | `History` | Sidebar navegación |
| Ayuda | `HelpCircle` | Sidebar navegación |
| Usuario | `User` | Header/perfil |
| Salir | `LogOut` | Menú de usuario |
| Configuración | `Settings` | Menú de usuario (futuro) |

---

### 📄 Iconos de Documentos

| Concepto | Icono Lucide | Uso |
|----------|--------------|-----|
| PDF/Documento | `FileText` | Archivos en lista, vista de fuente |
| Página | `File` | Referencia a página específica |
| Fuente/Link | `Link` | Link externo, ver fuente |
| Cita textual | `Quote` | Citaciones, extractos textuales |

---

## Ejemplos de Uso por Contexto

### Botón con Icono

```tsx
<button className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-md">
  <Plus size={20} />
  Analizar nuevo pliego
</button>
```

### Badge de Estado

```tsx
<span className="inline-flex items-center gap-1 px-2 py-1 rounded bg-warning-light text-warning">
  <AlertTriangle size={16} />
  ANALIZADO
</span>
```

### Campo con Confianza

```tsx
<div className="flex items-start gap-2 p-3 border-l-4 border-success bg-success-light">
  <CheckCircle size={20} className="text-success flex-shrink-0" />
  <div>
    <p className="font-semibold">Plazo de entrega</p>
    <p>30 días corridos desde apertura</p>
  </div>
</div>
```

### Loading Spinner

```tsx
<div className="flex items-center gap-2 text-gray-600">
  <Loader2 size={20} className="animate-spin" />
  <span>Analizando documentos...</span>
</div>
```

### Card de Categoría Crítica

```tsx
<div className="flex items-center gap-2 p-4 border-l-4 border-critical bg-critical-light">
  <AlertCircle size={24} className="text-critical" />
  <div>
    <h3 className="font-semibold">Plazos clave ⭐ CRÍTICA</h3>
    <p className="text-sm">Sin revisar · 2 no encontrados</p>
  </div>
</div>
```

### Menú de Acciones

```tsx
<button className="p-2 rounded hover:bg-gray-100">
  <MoreVertical size={20} className="text-gray-600" />
</button>
```

### Input con Búsqueda

```tsx
<div className="relative">
  <Search size={20} className="absolute left-3 top-2.5 text-gray-400" />
  <input 
    type="text"
    placeholder="Buscar por pliego u organismo..."
    className="pl-10 pr-4 py-2 border rounded-md w-full"
  />
</div>
```

---

## Guidelines de Implementación

### ✅ DO:

- Usa `md` (20px) como tamaño default
- Aplica colores con clases Tailwind (`text-success`, `text-error`)
- Usa `animate-spin` con `Loader2` para loading states
- Mantén consistencia: mismo icono para mismo concepto
- Usa `flex items-center gap-2` para alinear icono + texto

### ❌ DON'T:

- No mezcles iconos de otras librerías (FontAwesome, Material, etc.)
- No uses emojis nativos como iconos funcionales
- No uses tamaños fuera del sistema (16, 20, 24, 32)
- No cambies el mapeo sin actualizar esta referencia
- No olvides accessibility: agrega `aria-label` en iconos sin texto

---

## Accesibilidad

### Iconos decorativos (con texto visible):

```tsx
<button>
  <FileText size={20} aria-hidden="true" />
  Ver documento
</button>
```

### Iconos funcionales (sin texto):

```tsx
<button aria-label="Cerrar modal">
  <X size={20} />
</button>
```

### Loading states:

```tsx
<div role="status" aria-live="polite">
  <Loader2 size={20} className="animate-spin" />
  <span className="sr-only">Cargando...</span>
</div>
```

---

## Recursos Adicionales

- **Explorar todos los iconos:** https://lucide.dev/icons
- **Guía de uso:** https://lucide.dev/guide/packages/lucide-react
- **Repositorio GitHub:** https://github.com/lucide-icons/lucide
- **DESIGN.md completo:** [Ver contrato visual](./DESIGN.md)
- **00-UX-SPECIFICATIONS.md:** [Ver especificaciones completas](./00-UX-SPECIFICATIONS.md)

---

**Última actualización:** 2026-07-31  
**Versión del sistema:** CedIA v1.0  
**Mantenido por:** Equipo de Diseño UX
