---
colors:
  # Colores corporativos CedIA
  primary: "#2b6aae"
  primary_light: "#75e1d2"
  primary_turquoise: "#52a4ab"
  primary_teal: "#3e8296"
  
  # Colores del sistema (integrados con corporativos)
  primary_blue: "#2563EB"
  primary_blue_dark: "#1D4ED8"
  primary_blue_light: "#DBEAFE"
  
  # Colores de estado
  success: "#10B981"
  success_light: "#D1FAE5"
  warning: "#F59E0B"
  warning_light: "#FEF3C7"
  error: "#DC2626"
  error_light: "#FEE2E2"
  info: "#3B82F6"
  info_light: "#DBEAFE"
  critical: "#EA580C"
  critical_light: "#FFEDD5"
  
  # Escala de grises
  gray_50: "#F9FAFB"
  gray_100: "#F3F4F6"
  gray_200: "#E5E7EB"
  gray_300: "#D1D5DB"
  gray_400: "#9CA3AF"
  gray_500: "#6B7280"
  gray_600: "#4B5563"
  gray_700: "#374151"
  gray_900: "#111827"
  
  # Fondos y superficies
  background: "#F9FAFB"
  surface: "#FFFFFF"
  overlay: "rgba(0, 0, 0, 0.5)"

typography:
  families:
    sans: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    mono: "'Fira Code', 'SF Mono', Consolas, monospace"
  
  sizes:
    h1: "30px"
    h2: "24px"
    h3: "20px"
    h4: "18px"
    body_large: "16px"
    body: "14px"
    body_small: "12px"
    caption: "11px"
    button: "14px"
    badge: "12px"
  
  weights:
    regular: 400
    medium: 500
    semibold: 600
    bold: 700
  
  line_heights:
    tight: 1.2
    snug: 1.3
    normal: 1.4
    relaxed: 1.5

rounded:
  sm: "4px"
  md: "8px"
  lg: "12px"
  full: "9999px"

spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  "2xl": "48px"
  "3xl": "64px"

shadows:
  sm: "0 1px 2px rgba(0, 0, 0, 0.05)"
  md: "0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06)"
  lg: "0 10px 15px rgba(0, 0, 0, 0.1), 0 4px 6px rgba(0, 0, 0, 0.05)"
  xl: "0 20px 25px rgba(0, 0, 0, 0.1), 0 10px 10px rgba(0, 0, 0, 0.04)"

components:
  button:
    primary:
      background: "{colors.primary_blue}"
      color: "#FFFFFF"
      hover_background: "{colors.primary_blue_dark}"
      padding_md: "10px 16px"
      padding_sm: "8px 12px"
      padding_lg: "12px 24px"
      border_radius: "{rounded.md}"
      font_size: "{typography.sizes.button}"
      font_weight: "{typography.weights.semibold}"
      height_sm: "32px"
      height_md: "40px"
      height_lg: "48px"
    
    secondary:
      background: "#FFFFFF"
      color: "{colors.gray_700}"
      border: "1px solid {colors.gray_200}"
      hover_background: "{colors.gray_50}"
      
    danger:
      background: "{colors.error}"
      color: "#FFFFFF"
      hover_background: "#B91C1C"
      
    ghost:
      background: "transparent"
      color: "{colors.primary_blue}"
      hover_decoration: "underline"
  
  input:
    background: "#FFFFFF"
    border: "1px solid {colors.gray_200}"
    border_radius: "{rounded.md}"
    padding: "10px 12px"
    height: "40px"
    font_size: "{typography.sizes.body}"
    focus_border: "{colors.primary_blue}"
    error_border: "{colors.error}"
    disabled_background: "{colors.gray_50}"
  
  badge:
    padding: "4px 8px"
    border_radius: "{rounded.sm}"
    font_size: "{typography.sizes.badge}"
    font_weight: "{typography.weights.bold}"
    text_transform: "uppercase"
    
    status:
      queue:
        background: "{colors.gray_100}"
        color: "{colors.gray_600}"
      analyzing:
        background: "{colors.primary_blue_light}"
        color: "{colors.primary_blue}"
      analyzed:
        background: "{colors.warning_light}"
        color: "{colors.warning}"
      validated:
        background: "{colors.success_light}"
        color: "{colors.success}"
      error:
        background: "{colors.error_light}"
        color: "{colors.error}"
      cancelled:
        background: "{colors.gray_100}"
        color: "{colors.gray_500}"
    
    confidence:
      high:
        background: "{colors.success_light}"
        color: "{colors.success}"
      medium:
        background: "{colors.warning_light}"
        color: "{colors.warning}"
      low:
        background: "{colors.critical_light}"
        color: "{colors.critical}"
  
  card:
    background: "{colors.surface}"
    border: "1px solid {colors.gray_200}"
    border_radius: "{rounded.md}"
    padding: "{spacing.md}"
    shadow: "{shadows.md}"
    hover_shadow: "{shadows.lg}"
    
    conflict:
      border_left: "4px solid {colors.error}"
      background: "{colors.error_light}"
    warning:
      border_left: "4px solid {colors.warning}"
      background: "{colors.warning_light}"
    success:
      border_left: "4px solid {colors.success}"
      background: "{colors.success_light}"
    critical:
      border_left: "4px solid {colors.critical}"
      background: "{colors.critical_light}"
  
  modal:
    overlay_background: "{colors.overlay}"
    background: "{colors.surface}"
    max_width: "600px"
    border_radius: "{rounded.lg}"
    padding: "{spacing.lg}"
    shadow: "{shadows.xl}"
  
  toast:
    width_min: "300px"
    width_max: "400px"
    padding: "{spacing.md}"
    border_radius: "{rounded.md}"
    shadow: "{shadows.lg}"
    duration: "4000ms"
  
  sidebar:
    width: "240px"
    width_collapsed: "64px"
    background: "{colors.surface}"
    border_right: "1px solid {colors.gray_200}"
    
    item_active:
      background: "{colors.primary_blue_light}"
      color: "{colors.primary_blue}"
      border_left: "4px solid {colors.primary_blue}"
    item_hover:
      background: "{colors.gray_50}"

layout:
  breakpoints:
    xs: "640px"
    sm: "640px"
    md: "768px"
    lg: "1024px"
    xl: "1440px"
  
  content_max_width: "1920px"
  two_column_split: "60% / 40%"

transitions:
  duration: "200ms"
  easing: "ease-in-out"
  properties: "opacity, transform, background-color"

icons:
  library: "Lucide React"
  package: "lucide-react"
  version: "^0.460.0"
  
  sizes:
    sm: "16px"
    md: "20px"
    lg: "24px"
    xl: "32px"
  
  # Mapeo de iconos del sistema
  system:
    document: "FileText"
    calendar: "Calendar"
    clipboard: "ClipboardCheck"
    search: "Search"
    menu: "List"
    more_vertical: "MoreVertical"
    chevron_down: "ChevronDown"
    arrow_left: "ArrowLeft"
    arrow_right: "ArrowRight"
    refresh: "RefreshCw"
    upload: "Upload"
    download: "Download"
    trash: "Trash2"
    edit: "Edit"
    eye: "Eye"
    plus: "Plus"
    x: "X"
    user: "User"
    settings: "Settings"
  
  # Iconos de estado
  status:
    success: "CheckCircle"
    error: "XCircle"
    warning: "AlertTriangle"
    info: "Info"
    critical: "AlertCircle"
    pending: "Clock"
    processing: "Loader2"
  
  # Iconos de confianza (campos)
  confidence:
    high: "CheckCircle"
    medium: "Info"
    low: "AlertTriangle"
    conflict: "XCircle"
    not_found: "AlertTriangle"
    not_applicable: "Info"
  
  # Iconos de navegación
  navigation:
    dashboard: "LayoutDashboard"
    history: "History"
    help: "HelpCircle"
    logout: "LogOut"
  
  # Iconos de documentos
  document:
    pdf: "FileText"
    page: "File"
    source: "Link"
    citation: "Quote"
---

# Brand & Style

## Identity

**CedIA** es el Sistema de Análisis de Pliegos de Licitación desarrollado para profesionales que necesitan extraer, validar y revisar información crítica de documentos de licitaciones públicas de forma confiable y transparente.

La identidad visual de CedIA se construye sobre tres pilares:

- **Profesionalismo:** Una estética limpia, minimalista y enfocada en datos que transmite confianza y seriedad
- **Transparencia:** Toda extracción muestra su fuente verificable; los conflictos se exponen claramente
- **Claridad:** La información se presenta de forma directa, priorizando la legibilidad y la acción

El sistema visual combina:
- Colores corporativos azules y turquesas que evocan confiabilidad y tecnología
- Tipografía clara y funcional (Inter) optimizada para lectura de datos
- Espaciado generoso que permite foco y reduce fatiga visual
- Jerarquía visual fuerte que guía al usuario hacia lo crítico primero

---

## Colors

### Primary Colors — Identidad CedIA

Los colores corporativos establecen la identidad de marca:

- **CedIA Blue** `#2b6aae` — Color primario corporativo, usado en branding y navegación principal
- **Turquoise Light** `#75e1d2` — Acento corporativo para estados positivos
- **Turquoise Medium** `#52a4ab` — Variante media para elementos secundarios
- **Teal** `#3e8296` — Acento oscuro para profundidad

### System Colors — Interacción

Los colores del sistema se integran con los corporativos para acciones e interacción:

- **Primary Blue** `#2563EB` — Botones, links, estados activos
- **Primary Blue Dark** `#1D4ED8` — Hover states
- **Primary Blue Light** `#DBEAFE` — Fondos suaves, highlights

### Status Colors — Feedback Semántico

Comunican estados del sistema de forma universal:

- **Success** `#10B981` — Validado, confianza alta, acciones completadas
- **Warning** `#F59E0B` — Analizado (falta validar), confianza media
- **Error** `#DC2626` — Conflictos, errores, validación fallida
- **Critical** `#EA580C` — Categorías críticas que requieren atención inmediata
- **Info** `#3B82F6` — Información neutral, ayuda contextual

### Neutrals — Estructura y Contenido

Escala de grises de 50 a 900 para estructura, texto y capas:

- **Gray 50** `#F9FAFB` — Background principal de la aplicación
- **Gray 100-200** — Bordes sutiles, superficies secundarias
- **Gray 300-400** — Bordes destacados, texto secundario
- **Gray 500-600** — Texto deshabilitado, iconos secundarios
- **Gray 700-900** — Texto principal, títulos, énfasis

**Uso de Color:**
- Los colores corporativos (CedIA Blue family) se usan en branding, navegación y elementos de marca
- Los colores de sistema (Primary Blue) se usan en interacciones, botones, enlaces
- Los colores de estado siempre comunican feedback semántico consistente
- Los neutrales construyen jerarquía y estructura sin competir con la información

---

## Typography

### Font Families

**Inter** es la tipografía principal del sistema:

```
font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
```

**Características:**
- Sans-serif humanista optimizada para legibilidad en pantalla
- Altura-x generosa que mejora legibilidad en tamaños pequeños
- Kerning consistente para tablas y listas de datos
- Soporte completo para español (acentos, ñ)

**Fira Code** para contenido monoespaciado (citas de documento, datos estructurados):

```
font-family: 'Fira Code', 'SF Mono', Consolas, monospace;
```

### Type Scale

| Element | Size | Weight | Line Height | Use Case |
|---------|------|--------|-------------|----------|
| **H1** | 30px | Bold (700) | 1.2 | Títulos de página principales |
| **H2** | 24px | Semibold (600) | 1.3 | Subtítulos de sección |
| **H3** | 20px | Semibold (600) | 1.4 | Encabezados de card |
| **H4** | 18px | Semibold (600) | 1.4 | Subsecciones, nombres de campo |
| **Body Large** | 16px | Regular (400) | 1.5 | Contenido destacado, intro |
| **Body** | 14px | Regular (400) | 1.5 | Texto principal, default |
| **Body Small** | 12px | Regular (400) | 1.4 | Metadata, timestamps |
| **Caption** | 11px | Regular (400) | 1.3 | Labels muy secundarios |
| **Button** | 14px | Semibold (600) | 1.0 | Texto de botones |
| **Badge** | 12px | Bold (700) | 1.0 | Estados, tags (uppercase) |

### Text Colors

- **Principal:** Gray 900 `#111827` — Títulos, contenido principal
- **Secundario:** Gray 600 `#4B5563` — Texto de apoyo, metadata
- **Deshabilitado:** Gray 400 `#9CA3AF` — Estados inactivos
- **Links:** Primary Blue `#2563EB` — Enlaces, acciones
- **Error:** Error Red `#DC2626` — Mensajes de error

### Hierarchy Guidelines

- Use un solo H1 por página (título principal)
- H2 para secciones principales, H3 para subsecciones
- Cuerpo de texto siempre en Body (14px)
- Metadata y timestamps en Body Small (12px)
- Evite más de 3 niveles de jerarquía en una vista

---

## Layout & Spacing

### Spacing System

Sistema de espaciado basado en múltiplos de **4px**:

```
xs:  4px  — Padding mínimo, gaps entre elementos muy cercanos
sm:  8px  — Padding de badges, gaps entre items de lista
md:  16px — Padding de componentes (default), gaps entre cards
lg:  24px — Márgenes entre secciones relacionadas
xl:  32px — Separación de bloques principales
2xl: 48px — Separación de secciones mayores
3xl: 64px — Márgenes de página, héroes
```

**Aplicación:**
- Componentes internos: `md` (16px) padding por defecto
- Entre elementos relacionados: `sm-md` (8-16px) gap
- Entre secciones: `lg-xl` (24-32px) margin
- Entre bloques independientes: `2xl` (48px) margin

### Grid System

**Desktop (≥1024px):**
- 12 columnas con gap de 24px
- Márgenes laterales: 32px
- Contenido máximo: 1920px centrado

**Layout de dos columnas (pantalla de detalle):**
- Resultados: 60% del ancho disponible
- Visor PDF: 40% del ancho disponible
- Gap entre columnas: 24px

### Sidebar Navigation

- **Ancho extendido:** 240px
- **Ancho colapsado:** 64px (solo iconos)
- **Posición:** Fixed left
- **Altura:** 100vh

### Responsive Breakpoints

```
xs:  <640px  — Móviles (soporte mínimo)
sm:  ≥640px  — Móviles grandes
md:  ≥768px  — Tablets verticales
lg:  ≥1024px — Laptops, tablets horizontales (TARGET)
xl:  ≥1440px — Monitores grandes
```

**Estrategia:** Desktop-first, optimizado para pantallas ≥1024px. Soporte básico para móvil sin optimización completa en MVP.

---

## Elevation & Depth

### Shadow System

Las sombras crean jerarquía visual y profundidad:

```css
/* sm — Elementos sutiles (inputs, badges) */
box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);

/* md — Cards en reposo (default) */
box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1), 
            0 1px 2px rgba(0, 0, 0, 0.06);

/* lg — Cards hover, dropdowns */
box-shadow: 0 10px 15px rgba(0, 0, 0, 0.1), 
            0 4px 6px rgba(0, 0, 0, 0.05);

/* xl — Modales, overlays */
box-shadow: 0 20px 25px rgba(0, 0, 0, 0.1), 
            0 10px 10px rgba(0, 0, 0, 0.04);
```

**Aplicación:**
- Cards en reposo: `md`
- Cards hover/clickeable: `lg`
- Modales y overlays: `xl`
- Inputs y elementos sutiles: `sm`

### Layering

Z-index scale para apilar elementos:

```
Base content:    0
Sticky headers:  10
Dropdowns:       100
Sidebar:         200
Modals:          500
Modal overlay:   499
Toasts:          600
```

---

## Shapes

### Border Radius

Los bordes redondeados suavizan la estética y mejoran la percepción de profesionalismo:

```
sm:   4px   — Badges, tags, pequeños elementos
md:   8px   — Botones, inputs, cards (default)
lg:   12px  — Modales, paneles grandes
full: 9999px — Avatares, pills
```

**Uso:**
- Componentes pequeños (badges, chips): `sm` (4px)
- Componentes interactivos (botones, inputs, cards): `md` (8px)
- Paneles y modales: `lg` (12px)
- Elementos circulares (avatares): `full`

### Borders

Anchos de borde estandarizados:

```
Default: 1px  — Mayoría de los casos
Accent:  4px  — Borde izquierdo de cards con estado (crítico, error, etc.)
```

**Colores:**
- Default: Gray 200 `#E5E7EB`
- Hover: Gray 300 `#D1D5DB`
- Focus: Primary Blue `#2563EB`
- Error: Error Red `#DC2626`
- Critical: Critical Orange `#EA580C`

---

## Icons

### Icon Library

**CedIA utiliza [Lucide React](https://lucide.dev) como librería de iconos.**

**Instalación:**
```bash
npm install lucide-react
```

**Importación:**
```typescript
import { FileText, AlertTriangle, CheckCircle } from 'lucide-react'
```

### Icon Sizes

| Size | Dimensión | Uso |
|------|-----------|-----|
| **sm** | 16px | Inline con texto, badges |
| **md** | 20px | Botones, inputs (default) |
| **lg** | 24px | Headers, navegación |
| **xl** | 32px | Estados vacíos, ilustraciones |

**Uso:**
```tsx
<FileText size={20} /> // md (default)
<AlertTriangle size={16} className="text-error" />
```

### Icon Mapping

#### System Icons
| Nombre | Componente Lucide | Uso |
|--------|-------------------|-----|
| Documento | `FileText` | Archivos, pliegos |
| Calendario | `Calendar` | Fechas |
| Clipboard | `ClipboardCheck` | Progreso, revisión |
| Búsqueda | `Search` | Buscadores |
| Menú | `List` | Menú principal |
| Más opciones | `MoreVertical` | Menús contextuales |
| Expandir | `ChevronDown` | Dropdowns, colapsables |
| Volver | `ArrowLeft` | Navegación atrás |
| Recargar | `RefreshCw` | Re-analizar |
| Subir | `Upload` | Upload de archivos |

#### Status Icons
| Estado | Componente Lucide | Color |
|--------|-------------------|-------|
| Éxito | `CheckCircle` | Success `#10B981` |
| Error | `XCircle` | Error `#DC2626` |
| Advertencia | `AlertTriangle` | Warning `#F59E0B` |
| Info | `Info` | Info `#3B82F6` |
| Crítico | `AlertCircle` | Critical `#EA580C` |
| En proceso | `Loader2` | Primary Blue (animado) |
| Pendiente | `Clock` | Gray `#6B7280` |

#### Confidence Level Icons
| Nivel | Componente Lucide | Color |
|-------|-------------------|-------|
| Confianza Alta | `CheckCircle` | Success |
| Confianza Media | `Info` | Info Blue |
| Confianza Baja | `AlertTriangle` | Critical Orange |
| En Conflicto | `XCircle` | Error Red |
| No Encontrado | `AlertTriangle` | Warning |
| No Aplica | `Info` | Info Blue |

#### Navigation Icons
| Elemento | Componente Lucide |
|----------|-------------------|
| Dashboard | `LayoutDashboard` |
| Historial | `History` |
| Ayuda | `HelpCircle` |
| Salir | `LogOut` |
| Usuario | `User` |
| Configuración | `Settings` |

### Icon Guidelines

**DO:**
- ✓ Usa tamaño `md` (20px) como default
- ✓ Alinea iconos con texto usando flexbox
- ✓ Aplica colores mediante clases Tailwind (`text-error`, `text-success`)
- ✓ Usa `Loader2` con animación `animate-spin` para loading
- ✓ Mantén consistencia: mismo icono para mismo concepto

**DON'T:**
- ✗ No mezcles iconos de múltiples librerías
- ✗ No uses emojis como iconos funcionales
- ✗ No uses tamaños fuera del sistema (16, 20, 24, 32)
- ✗ No cambies iconos arbitrariamente sin consultar el mapeo

### Usage Examples

**Botón con icono:**
```tsx
<button className="flex items-center gap-2">
  <Plus size={20} />
  Analizar nuevo pliego
</button>
```

**Badge con icono:**
```tsx
<span className="inline-flex items-center gap-1 px-2 py-1">
  <AlertTriangle size={16} className="text-warning" />
  No encontrado
</span>
```

**Loading state:**
```tsx
<Loader2 size={20} className="animate-spin text-primary" />
```

---

## Components

### Buttons

**Primary Button**
- Fondo: Primary Blue `#2563EB`
- Texto: Blanco
- Hover: Primary Blue Dark `#1D4ED8`
- Altura: 40px (M), 32px (S), 48px (L)
- Padding: 10px 16px (M)
- Border radius: 8px
- Font: 14px, Semibold (600)

**Secondary Button**
- Fondo: Blanco
- Borde: 1px Gray 200
- Texto: Gray 700
- Hover: fondo Gray 50

**Danger Button**
- Fondo: Error Red `#DC2626`
- Texto: Blanco
- Hover: Red Dark `#B91C1C`

**Ghost Button**
- Sin fondo ni borde
- Texto: Primary Blue
- Hover: underline

**Estados:**
- Disabled: Opacidad 50%, cursor not-allowed
- Loading: Spinner animado, texto "Cargando..."

### Inputs

**Text Input**
- Altura: 40px
- Borde: 1px Gray 200
- Border radius: 8px
- Padding: 10px 12px
- Font: 14px, Regular
- Focus: borde Primary Blue
- Error: borde Error Red + mensaje debajo

**Textarea**
- Igual que text input
- Mínimo 80px alto
- Resizable verticalmente

**Select/Dropdown**
- Igual que input
- Icono chevron-down a la derecha
- Opciones en menú flotante con shadow lg

**Checkbox**
- Tamaño: 20x20px
- Borde: 1px Gray 300
- Checked: fondo Primary Blue, checkmark blanco

**Radio Button**
- Tamaño: 20x20px circular
- Borde: 1px Gray 300
- Selected: centro Primary Blue filled

### Badges

**Status Badges:**

| Estado | Color Fondo | Color Texto | Icono (Lucide) |
|--------|-------------|-------------|----------------|
| En cola | Gray 100 | Gray 600 | `Clock` |
| Analizando | Blue Light | Primary Blue | `Loader2` (animado) |
| Analizado | Warning Light | Warning | `AlertTriangle` |
| Validado | Success Light | Success | `CheckCircle` |
| Error | Error Light | Error | `XCircle` |
| Cancelado | Gray 100 | Gray 500 | `X` |

**Confidence Badges:**

| Nivel | Color Fondo | Color Texto | Icono (Lucide) |
|-------|-------------|-------------|----------------|
| Alta | Success Light | Success | `CheckCircle` |
| Media | Warning Light | Warning | `Info` |
| Baja | Critical Light | Critical | `AlertTriangle` |

**Formato:**
- Padding: 4px 8px
- Border radius: 4px
- Font: 12px, Bold (700)
- Text transform: UPPERCASE

### Cards

**Basic Card**
- Fondo: White
- Borde: 1px Gray 200
- Border radius: 8px
- Padding: 16px
- Shadow: md

**Hover Card (clickeable)**
- Hover: shadow lg, cursor pointer
- Transition: 200ms ease-in-out

**Status Cards (con borde lateral)**

| Estado | Borde izquierdo | Fondo |
|--------|-----------------|-------|
| Conflicto | 4px Error Red | Error Light |
| Advertencia | 4px Warning | Warning Light |
| Crítico | 4px Critical Orange | Critical Light |
| Exitoso | 4px Success | Success Light |

### Modals

**Estructura:**
```
[Overlay: rgba(0,0,0,0.5) full screen]

┌────────────────────────────────┐
│ [Título]                  [X]  │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                │
│ [Contenido]                    │
│                                │
│ [Botones de acción]            │
└────────────────────────────────┘
```

- Max width: 600px
- Centrado vertical y horizontal
- Border radius: 12px
- Padding: 24px
- Shadow: xl
- Animación: fade + scale (95% → 100%)

### Toasts

**Posición:** Top-right
**Ancho:** 300-400px
**Auto-dismiss:** 4 segundos
**Shadow:** lg

| Tipo | Color Fondo | Color Texto | Icono |
|------|-------------|-------------|-------|
| Success | Success Light | Success | ✓ |
| Error | Error Light | Error | ✗ |
| Warning | Warning Light | Warning | ⚠️ |
| Info | Info Light | Info | ℹ️ |

### Sidebar

**Dimensiones:**
- Ancho: 240px (extendido), 64px (colapsado)
- Altura: 100vh
- Posición: Fixed left

**Item de navegación:**
- Padding: 12px 16px
- Border radius: 8px
- Font: 14px, Medium (500)

**Estado activo:**
- Fondo: Primary Blue Light `#DBEAFE`
- Texto: Primary Blue `#2563EB`
- Borde izquierdo: 4px Primary Blue

**Estado hover:**
- Fondo: Gray 50 `#F9FAFB`
- Cursor: pointer

### Tooltips

- Fondo: Gray 900 `#1F2937`
- Texto: Blanco, 14px
- Padding: 8px 12px
- Border radius: 4px
- Shadow: md
- Flecha apuntando al elemento
- Aparece después de 500ms hover

---

## Transitions & Animations

### Duration & Easing

```css
/* Standard transition */
transition: all 200ms ease-in-out;

/* Properties to animate */
opacity, transform, background-color, box-shadow
```

### Loaders

**Spinner**
- Animación: rotate 360deg
- Duración: 1s linear infinite
- Tamaño: 20px (inline), 32px (page)

**Skeleton Loaders**
- Animación: shimmer de izquierda a derecha
- Duración: 1.5s ease-in-out infinite
- Fondo: gradient Gray 100 → Gray 200 → Gray 100

**Progress Bar**
- Animación de llenado smooth
- Transition: width 300ms ease-out

### Micro-interactions

- **Buttons:** scale(1.02) en hover
- **Cards:** elevación de shadow en hover
- **Modales:** fade in (0 → 1) + scale (95% → 100%)
- **Toasts:** slide-in from top-right
- **Checkmark success:** scale bounce (0 → 1.2 → 1)

---

## Accessibility

### WCAG 2.1 Level AA

**Contraste de color:**
- Texto normal (14px): mínimo 4.5:1
- Texto grande (18px+): mínimo 3:1
- Elementos de interfaz: mínimo 3:1

**Navegación por teclado:**
- Todos los elementos interactivos accesibles por Tab
- Focus visible con outline de 2px Primary Blue
- Skip to main content link
- Escape cierra modales

**Lectores de pantalla:**
- Semantic HTML (nav, main, article, aside)
- ARIA labels en iconos sin texto
- ARIA live regions para toasts y notificaciones dinámicas
- Alt text descriptivo en imágenes

**Estados de interacción:**
- Focus states claramente visibles
- Estados disabled con aria-disabled
- Mensajes de error asociados con aria-describedby

---

## Iconography

**Librería:** [Lucide Icons](https://lucide.dev/)

**Tamaños:**
```
sm: 16px — Inline con texto
md: 20px — Default, botones
lg: 24px — Headers, énfasis
xl: 32px — Ilustraciones, placeholders
```

**Colores:**
- Heredan del texto padre
- Estados específicos: Success, Warning, Error
- Siempre acompañados de texto (excepto universales: X, ✓, ⚙️)

**Iconos comunes:**
- 📄 Document
- ⏳ Clock (en cola)
- ⚙️ Settings/Processing
- ✓ Check (éxito)
- ✗ X (error, cerrar)
- ⚠️ Alert Triangle (advertencia)
- ℹ️ Info
- 📊 Chart (análisis)
- 🔍 Search
- ← → Arrows (navegación)
- ⋮ More (menú)

---

## Do's and Don'ts

### ✅ Do's

**Color**
- ✅ Usa colores corporativos (CedIA Blue family) para branding y navegación
- ✅ Usa colores de sistema (Primary Blue) para interacciones y botones
- ✅ Reserva colores de estado (Success, Warning, Error) solo para feedback semántico
- ✅ Mantén contraste mínimo 4.5:1 para texto normal
- ✅ Usa Gray 50 como fondo principal para reducir fatiga visual

**Typography**
- ✅ Usa un solo H1 por página
- ✅ Mantén el texto principal en 14px (Body) para legibilidad
- ✅ Usa line-height de 1.5 en texto de lectura
- ✅ Limita líneas de texto a 75 caracteres para legibilidad óptima

**Spacing**
- ✅ Usa múltiplos de 4px para consistencia
- ✅ Da espacio generoso alrededor de información crítica
- ✅ Agrupa elementos relacionados con gaps pequeños (8-16px)
- ✅ Separa secciones independientes con gaps grandes (24-48px)

**Components**
- ✅ Usa Primary Button para la acción principal única por pantalla
- ✅ Muestra estados de carga con spinners o skeleton loaders
- ✅ Proporciona feedback inmediato con toasts
- ✅ Usa modales solo para decisiones críticas o flujos que requieren foco
- ✅ Habilita botones solo cuando la acción es posible

**Layout**
- ✅ Optimiza para pantallas ≥1024px (target principal)
- ✅ Usa dos columnas (60/40) para resultados + visor PDF
- ✅ Mantén navegación sidebar consistente en todas las pantallas
- ✅ Colapsa sidebar a 64px en pantallas medianas

### ❌ Don'ts

**Color**
- ❌ No uses color como único indicador de estado (añade iconos/texto)
- ❌ No mezcles colores corporativos con colores de estado en el mismo contexto
- ❌ No uses Error Red para elementos que no sean errores
- ❌ No uses más de 3 colores distintos en un mismo componente

**Typography**
- ❌ No uses múltiples H1 en una página
- ❌ No uses tamaños de fuente menores a 12px
- ❌ No uses más de 3 pesos de fuente en un mismo contexto
- ❌ No uses line-height menor a 1.2 en texto de lectura
- ❌ No uses UPPERCASE para texto largo (solo badges y labels cortos)

**Spacing**
- ❌ No uses valores arbitrarios fuera del sistema de 4px
- ❌ No coloques elementos clickeables muy cerca (mínimo 8px gap)
- ❌ No dejes secciones sin separación visual clara

**Components**
- ❌ No uses múltiples Primary Buttons en la misma vista
- ❌ No ocultes información crítica en tooltips
- ❌ No uses modales para información no-crítica
- ❌ No dejes estados de loading sin mensaje explicativo
- ❌ No uses Ghost Buttons para acciones primarias

**Layout**
- ❌ No fuerces scroll horizontal
- ❌ No coloques acciones críticas fuera del viewport inicial
- ❌ No uses layouts asimétricos sin justificación
- ❌ No ocultes navegación principal en móvil sin indicador claro

**Accessibility**
- ❌ No dependas solo de color para transmitir información
- ❌ No ocultes el focus outline (reemplázalo con uno visible)
- ❌ No uses placeholders como labels
- ❌ No deshabilites zoom en móvil
- ❌ No uses texto en imágenes sin alternativa accesible

### Critical Don'ts — Never Do This

⛔ **NUNCA ocultes un conflicto** — Si hay valores contradictorios, exponlos siempre  
⛔ **NUNCA permitas validar sin revisar categorías críticas** — Plazos, Garantías, Causales deben revisarse  
⛔ **NUNCA muestres confianza sin fuente** — Todo valor extraído debe indicar su origen  
⛔ **NUNCA uses animaciones largas (>300ms) en acciones críticas** — La velocidad importa  
⛔ **NUNCA ocultes el estado de procesamiento** — El usuario debe saber qué está pasando

---

## Version History

- **v1.0** (2026-07-31) — Documento inicial basado en PRD v2.0 y 00-UX-SPECIFICATIONS.md
- Sistema de diseño establecido para CedIA MVP
- Integración de colores corporativos con sistema de tokens
- Definición completa de componentes, tipografía y espaciado

---

**Maintainers:** Sally (UX Designer)  
**Status:** Active — Contrato visual definitivo del sistema  
**Next Review:** Post-MVP feedback iteration
