---
status: draft
created: 2026-07-31
updated: 2026-07-31
sources:
  - ../../_bmad-output/planning-artifacts/prds/prd-licitaciones-pi-2026-07-29/prd.md
  - 00-UX-SPECIFICATIONS.md
  - DESIGN.md
---

# EXPERIENCE.md — Contrato de Comportamiento e Interacción

**Sistema:** CedIA — Análisis Automático de Pliegos de Licitación  
**Usuario primario:** Ejecutivos Comerciales de Grupo CEDI  
**Objetivo:** Análisis de pliegos de 30+ páginas en minutos con transparencia radical

---

## 1. Foundation

### 1.1. Form Factor

**Plataforma primaria:** Web desktop (escritorio)  
**Resoluciones objetivo:** 1366×768 (mínimo) a 1920×1080+ (óptimo)  
**Navegadores soportados:** Chrome, Edge, Firefox, Safari (últimas 2 versiones)  

**Dispositivos secundarios:**
- **Tablets (landscape):** Experiencia completa con ajustes de layout
- **Móviles:** Solo consulta (no análisis nuevo ni edición)

**Contexto de uso:**
- Sesiones de revisión de 10-30 minutos
- Múltiples análisis en paralelo (tabs)
- Trabajo híbrido (oficina y remoto)
- Referencia cruzada con documentos externos

### 1.2. UI System Reference

**Framework:** React + TypeScript + Vite  
**Componentes:** Headless UI (Radix UI) + Tailwind CSS  
**Iconos:** [Lucide React](https://lucide.dev) (`lucide-react`)  
**Design Tokens:** Definidos en DESIGN.md — todos los valores visuales se referencian con notación `{token.path}`

**Principio de separación:**
- **DESIGN.md** = QUÉ se ve (colores, tipografía, tamaños, sombras, **mapeo de iconos**)
- **EXPERIENCE.md** = CÓMO funciona (interacciones, estados, transiciones, flujos)

### 1.3. El Diseño como Contrato

Este documento es el **contrato funcional** entre producto, diseño y desarrollo. Define:

✅ **Qué comportamientos están garantizados**  
✅ **Qué estados existen y cómo se transita entre ellos**  
✅ **Qué acciones están disponibles en cada contexto**  
✅ **Qué feedback recibe el usuario en cada acción**  
✅ **Qué validaciones se ejecutan en cada paso**

❌ **No incluye:** especificaciones visuales (esas están en DESIGN.md)

**Principios de interacción:**
1. **Honestidad primero:** El sistema nunca oculta incertidumbre
2. **Severidad guía atención:** Lo crítico se prioriza visualmente y funcionalmente
3. **Sin sorpresas:** Toda acción muestra preview o confirmación cuando hay riesgo
4. **Feedback inmediato:** Toda acción tiene respuesta visual instantánea
5. **Guía progresiva:** El usuario siempre sabe qué falta, qué revisar, qué hacer

---

## 2. Information Architecture

### 2.1. Jerarquía Global

```
CedIA
│
├── 📊 Dashboard (Historial)
│   ├── Buscador global
│   ├── Filtros (Fecha, Estado)
│   ├── Lista de análisis (cards)
│   │   └── Acciones por análisis
│   └── Paginación
│
├── ✨ Analizar Nuevo Pliego
│   ├── Paso 1: Subir archivos
│   │   ├── Drag & drop zone
│   │   ├── File picker
│   │   └── Validación cliente-side
│   ├── Paso 2: Designar principal (condicional)
│   ├── Paso 3: Confirmar
│   ├── Progreso (etapas nombradas)
│   └── → Detalle del análisis
│
└── 📄 Detalle del Análisis
    ├── Header (metadata del pliego)
    ├── Panel Izquierdo: 8 Categorías
    │   ├── Plazos clave ⭐ CRÍTICA
    │   ├── Garantías ⭐ CRÍTICA
    │   ├── Causales de rechazo ⭐ CRÍTICA
    │   ├── Objeto y alcance
    │   ├── Requisitos de admisibilidad
    │   ├── Criterios de evaluación
    │   ├── Anexos obligatorios
    │   └── Datos del procedimiento
    ├── Panel Derecho: Visor PDF
    │   ├── Navegación por páginas
    │   ├── Zoom
    │   ├── Selector de documento
    │   └── Resaltado de citas
    └── Footer: Botón Validar
```

### 2.2. Navegación Principal

**Sidebar izquierdo persistente:**
- Ancho: 240px (colapsable a 64px)
- Posición: Fixed, altura 100vh
- Orden vertical: Logo → Navegación → Usuario

**Items de navegación:**
1. Dashboard (icono + label)
2. Analizar Pliego (icono + label)
3. [Futuros: Radar, Chat IA, etc.]
4. Separador visual
5. Avatar + nombre usuario
6. Cerrar sesión

**Estados de navegación:**
- **Normal:** Texto {colors.gray_600}, fondo transparente
- **Hover:** Fondo {colors.gray_100}, cursor pointer
- **Activo:** Fondo {colors.primary_blue_light}, texto {colors.primary_blue}, borde izquierdo 4px {colors.primary_blue}

### 2.3. Breadcrumbs y Contexto

**Dashboard:** No requiere breadcrumb (es raíz)

**Análisis nuevo:** 
```
Dashboard > Analizar nuevo pliego > [Paso actual]
```

**Detalle:**
```
Dashboard > [Nombre del pliego]
```
Con botón "← Volver al historial" siempre visible.

### 2.4. Jerarquía de Información por Pantalla

**Nivel 1 (Global):**
- Sidebar + Header de página
- Usuario activo
- Contexto actual

**Nivel 2 (Acciones):**
- Acciones principales (botones CTA)
- Filtros y búsqueda
- Navegación secundaria

**Nivel 3 (Contenido):**
- Cards, listas, tablas
- Formularios
- Resultados de extracción

**Nivel 4 (Detalles):**
- Citas textuales
- Tooltips
- Modales de confirmación

---

## 3. Voice and Tone

### 3.1. Personalidad del Sistema

**CedIA habla como:**  
Un asistente profesional experimentado que conoce el dominio de licitaciones pero **nunca asume que entiende mejor que el usuario**. Es directo, honesto sobre sus limitaciones, y guía sin imponer.

**Características:**
- **Formal pero accesible:** "usted" → "vos", español rioplatense neutro
- **Transparente:** Admite incertidumbre, nunca la oculta
- **Orientado a la acción:** Dice QUÉ hacer, no solo QUÉ pasó
- **Respetuoso del tiempo:** Mensajes concisos, sin relleno

### 3.2. Principios de Microcopy

**✅ Hacer:**
- Usar verbos de acción: "Subir", "Revisar", "Validar"
- Explicar impacto: "Esta acción no se puede deshacer"
- Nombrar el problema Y la solución: "Este archivo pesa 68 MB. El máximo es 50 MB. Probá comprimirlo o dividirlo"
- Contextualizar estados: "Sin revisar" mejor que "Pendiente"

**❌ Evitar:**
- Tecnicismos sin explicación: "OCR fallido" → "No se pudo leer el texto escaneado"
- Culpar al usuario: "Error de validación" → "Falta completar estos campos"
- Vaguedad: "Algo salió mal" → "No se pudo subir el archivo. Verificá tu conexión"
- Falsa precisión: "87% de confianza" → "Confianza: Alta"

### 3.3. Ejemplos de Mensajes Clave

**Estados de análisis:**
```
✓ "Tu análisis está en cola, comenzará en breve"
✓ "Extrayendo texto del documento 2 de 3"
✓ "Analizando categorías (5 de 8 completas)"
✓ "¡Análisis completado! Revisá los resultados"
```

**Errores:**
```
❌ "Este archivo no es un PDF. Solo podemos analizar archivos PDF"
❌ "Este archivo pesa 68 MB. El máximo es 50 MB. Probá comprimirlo o dividirlo"
❌ "No se encontró información sobre el plazo de consultas en los documentos analizados"
❌ "No se pudo cargar el documento. Verificá tu conexión y volvé a intentar"
```

**Advertencias:**
```
⚠️ "Este análisis tiene 150 páginas y puede demorar hasta 12 minutos"
⚠️ "El análisis está demorando más de lo esperado pero continúa procesándose"
⚠️ "Antes de validar: Revisá las 3 categorías críticas y resolvé 2 conflictos pendientes"
```

**Confirmaciones:**
```
"¿Estás seguro que querés cancelar el análisis en curso?"
"¿Querés eliminar este análisis? Esta acción no se puede deshacer"
"¿Querés re-analizar este pliego? Se creará una nueva versión"
```

**Feedback de éxito:**
```
✓ "Análisis validado correctamente"
✓ "Conflicto resuelto"
✓ "Campo actualizado"
✓ "Categoría marcada como revisada"
```

### 3.4. Tratamiento de Estados Honestos

**Campo "No encontrado":**
```
"No se encontró información sobre [nombre campo] en los documentos analizados"
Acción: [Agregar manualmente]
```

**Campo "En conflicto":**
```
"Dos documentos tienen valores distintos para [nombre campo]"
Acción: [Resolver conflicto]
```

**Campo "Confianza baja":**
```
"Este valor tiene confianza baja. Verificá la cita antes de usarlo"
Acción: [Ver fuente] [Corregir]
```

**Categoría con error:**
```
"Error al analizar esta categoría. Intentá de nuevo o agregá los datos manualmente"
Acción: [Reintentar] [Agregar manualmente]
```

---

## 4. Component Patterns

### 4.1. Botones

**Tipos de acción:**

1. **Primario (CTA):**
   - Una sola acción primaria por contexto
   - Ejemplos: "Siguiente", "Iniciar análisis", "Validar análisis", "Guardar"
   - Visual: {components.button.primary}
   - Estados: Normal → Hover → Active → Loading → Disabled

2. **Secundario:**
   - Acciones complementarias, menos frecuentes
   - Ejemplos: "Cancelar", "Volver", "Ver más"
   - Visual: {components.button.secondary}

3. **Destructivo:**
   - Acciones irreversibles o de alto riesgo
   - Ejemplos: "Eliminar", "Cancelar análisis"
   - Visual: {components.button.danger}
   - Siempre requieren confirmación

4. **Ghost:**
   - Acciones terciarias, bajo énfasis
   - Ejemplos: "Ver fuente", "Expandir", links inline
   - Visual: {components.button.ghost}

**Comportamiento:**
- **Hover:** Cambio de color de fondo + cursor pointer
- **Focus:** Outline azul 2px (accesibilidad)
- **Active:** Escala 98% (feedback táctil)
- **Loading:** Spinner reemplaza texto, botón deshabilitado
- **Disabled:** Opacidad 40%, cursor not-allowed, tooltip explica por qué

### 4.2. Inputs y Formularios

**Text inputs:**
- Height: {components.input.height} (40px)
- Padding: {components.input.padding}
- Border: {components.input.border}
- Focus: Border cambia a {components.input.focus_border}, outline adicional para accesibilidad
- Error: Border {components.input.error_border} + mensaje debajo

**Validación:**
- **En tiempo real:** Solo después del primer blur (evita frustración)
- **Mensajes:** Debajo del campo, {colors.error}, icono ❌
- **Éxito:** Checkmark verde al lado del campo (opcional, solo si confirmación inmediata ayuda)

**File upload:**
- **Drag & drop zone:** Borde punteado, transición suave en hover/dragover
- **Dragover:** Borde azul sólido, fondo azul muy claro, escala 102%
- **Drop:** Animación de carga, validación inmediata
- **Multiple files:** Lista vertical de archivos con estado individual

**Ejemplo de estados en file upload:**
```
Estado inicial → Hover → Dragover → Drop → Validando → Válido/Inválido
```

### 4.3. Cards

**Card de análisis (Dashboard):**
- Background: {components.card.background}
- Border: {components.card.border}
- Border-radius: {components.card.border_radius}
- Shadow: {components.card.shadow}
- Hover: Shadow elevada {components.card.hover_shadow}, cursor pointer (si clickable)

**Card de categoría (Detalle):**
- Colapsable: Click en header expande/colapsa
- Header con iconografía de estado
- Borde izquierdo 4px según severidad:
  - Crítica sin revisar: {colors.critical}
  - Conflictos: {colors.error}
  - Revisada: {colors.success}
  - Normal: {colors.gray_200}

**Card de campo (dentro de categoría):**
- Background según estado:
  - Conflicto: {components.card.conflict.background}
  - No encontrado: {components.card.warning.background}
  - Confianza baja: {components.card.critical.background}
  - Normal: {components.card.background}

### 4.4. Modales

**Comportamiento:**
- Aparición: Fade-in overlay + scale-in del modal (200ms)
- Overlay: {components.modal.overlay_background}, click cierra modal
- Modal: Centrado, {components.modal.max_width}, padding {components.modal.padding}
- Focus trap: Tab navega solo dentro del modal
- Escape: Cierra el modal (equivale a "Cancelar")

**Tipos:**
1. **Confirmación destructiva:** "¿Estás seguro...?" + [Cancelar] [Confirmar destructivo]
2. **Formulario:** Inputs + [Cancelar] [Guardar]
3. **Resolución de conflicto:** Radio buttons + [Cancelar] [Confirmar]
4. **Información:** Solo lectura + [Cerrar]

### 4.5. Badges

**Estados de análisis:**
- En cola: {components.badge.status.queue}
- Analizando: {components.badge.status.analyzing} + animación de pulso
- Analizado: {components.badge.status.analyzed}
- Validado: {components.badge.status.validated}
- Error: {components.badge.status.error}
- Cancelado: {components.badge.status.cancelled}

**Confianza:**
- Alta: {components.badge.confidence.high}
- Media: {components.badge.confidence.medium}
- Baja: {components.badge.confidence.low}

### 4.6. Listas y Tablas

**Lista de análisis (Dashboard):**
- 20 items por página (configurable)
- Scroll vertical dentro del contenedor
- Skeleton loading mientras carga
- Estado vacío con ilustración + CTA

**Lista de campos (Categoría expandida):**
- Ordenados por severidad (conflictos → no encontrados → confianza baja → confianza media → confianza alta)
- Separadores visuales entre grupos de severidad
- Scroll interno si excede viewport

### 4.7. Tooltips y Popovers

**Tooltips:**
- Aparecen en hover después de 500ms
- Desaparecen al mover el mouse
- Texto conciso (máximo 2 líneas)
- Fondo {colors.gray_900}, texto blanco
- Flecha apuntando al elemento

**Popovers:**
- Click para abrir/cerrar
- Pueden contener acciones (botones)
- Click fuera cierra
- Flecha apuntando al trigger

---

## 5. State Patterns

### 5.1. Estados de Campo (4 estados)

**Estado máquina de campo:**

```
┌─────────────┐
│   Inicial   │ (vacío, antes de análisis)
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌──────────────┐
│  Extraído   │────→│  Modificado  │
└─────────────┘     └──────────────┘
       │                    │
       │                    │
┌─────────────┐             │
│No encontrado│             │
└─────────────┘             │
       │                    │
       │                    │
┌─────────────┐             │
│  No aplica  │             │
└─────────────┘             │
       │                    │
       │                    │
┌─────────────┐             │
│En conflicto │─────────────┘
└─────────────┘
       │
       ▼
┌─────────────┐
│  Resuelto   │ (sub-estado de En conflicto)
└─────────────┘
```

**1. EXTRAÍDO:**
- **Condición:** Sistema encontró el dato y tiene cita verificable
- **Propiedades:**
  - Valor: string/number/date
  - Cita: texto + archivo + página
  - Confianza: Alta | Media | Baja
- **Acciones disponibles:**
  - Ver fuente (abre PDF en página correcta)
  - Corregir (abre modal → transición a Modificado)
- **Visual:** Borde según confianza, icono según confianza

**2. NO ENCONTRADO:**
- **Condición:** Sistema no pudo determinar el dato
- **Propiedades:**
  - Razón: "No se encontró en documentos" | "Error de extracción"
- **Acciones disponibles:**
  - Agregar manualmente (abre modal → transición a Modificado)
- **Visual:** Borde {colors.warning}, icono ⚠️, fondo {colors.warning_light}

**3. NO APLICA:**
- **Condición:** Pliego declara explícitamente que no se exige, CON CITA
- **Propiedades:**
  - Cita: texto + archivo + página (obligatorio)
- **Acciones disponibles:**
  - Ver fuente
  - Corregir (si la interpretación fue incorrecta)
- **Visual:** Borde {colors.gray_300}, icono ℹ️, texto gris

**4. EN CONFLICTO:**
- **Condición:** Dos o más documentos dan valores contradictorios
- **Propiedades:**
  - Valores: array de {valor, cita, archivo, página, confianza}
- **Acciones disponibles:**
  - Resolver conflicto (abre modal → transición a Resuelto)
  - Ver cada fuente
- **Visual:** Borde {colors.error}, icono ❌, fondo {colors.error_light}
- **Sub-estado RESUELTO:**
  - Usuario eligió un valor
  - Se registra el descartado
  - Pasa a comportarse como Extraído (pero con registro de conflicto previo)

**5. MODIFICADO (meta-estado):**
- **Condición:** Usuario editó el valor (desde cualquier estado previo)
- **Propiedades:**
  - Valor actual: introducido por usuario
  - Valor original: del sistema
  - Modificado por: usuario
  - Modificado en: timestamp
  - Justificación: opcional
- **Acciones disponibles:**
  - Ver fuente original (si había)
  - Editar nuevamente
- **Visual:** Borde {colors.info}, icono ✏️, badge "MODIFICADO"

### 5.2. Estados de Categoría (2 estados + contadores)

**Estado principal:**

```
┌──────────────┐
│ Sin revisar  │ (inicial)
└──────┬───────┘
       │
       │ Usuario marca explícitamente
       │
       ▼
┌──────────────┐
│  Revisada    │
└──────┬───────┘
       │
       │ Cualquier edición en campos
       │
       └────────┐
                │
                ▼
        ┌──────────────┐
        │ Sin revisar  │
        └──────────────┘
```

**SIN REVISAR:**
- Estado inicial de toda categoría
- Se vuelve a este estado si el usuario modifica un campo (garantiza revisión de cambios)
- **Propiedades contadas:**
  - Total de campos: n
  - Extraídos: x
  - No encontrados: y
  - En conflicto: z
  - Confianza promedio: (suma confianzas) / n
- **Visual:** 
  - Si es crítica: Borde {colors.critical}, icono ⚠️, badge "⭐ CRÍTICA"
  - Si tiene conflictos: Borde {colors.error}, texto rojo destacado
  - Si no: Borde {colors.gray_300}

**REVISADA:**
- Usuario hizo click en "Marcar como revisada" después de revisar todos los campos
- **Propiedades:**
  - Timestamp de revisión
  - Usuario que revisó
- **Visual:** Borde {colors.success}, icono ✓, badge "REVISADA"

**FALLIDA (estado de error):**
- Error durante la extracción de esta categoría
- **Acciones disponibles:**
  - Reintentar
  - Agregar campos manualmente
- **Visual:** Borde rojo punteado, icono 🔴, mensaje de error

### 5.3. Estados de Análisis (ciclo de vida)

**Máquina de estados del análisis:**

```
┌─────────┐
│ En cola │
└────┬────┘
     │
     ▼
┌──────────────────┐    ┌───────────┐
│ Extrayendo texto │◄───│Reintentando│
└────┬─────────────┘    └───────────┘
     │                        ▲
     ▼                        │
┌──────────┐                 │
│Indexando │                 │
└────┬─────┘                 │
     │                        │
     ▼                        │
┌────────────┐               │
│Analizando  │───────────────┘ (si falla categoría)
│categorías  │
└────┬───────┘
     │
     ▼
┌─────────────┐
│Consolidando │
└──────┬──────┘
       │
       ▼
┌──────────┐      ┌────────────┐
│Analizado │─────→│ Validado   │
└────┬─────┘      └────────────┘
     │
     │ Re-análisis
     ▼
┌──────────────┐
│Nueva versión │
└──────────────┘

Estados terminales:
┌───────────┐  ┌───────┐
│Cancelado  │  │ Error │
└───────────┘  └───────┘
```

**EN COLA:**
- Análisis aceptado, esperando recursos
- **Visual:** Badge gris, icono reloj
- **Acción disponible:** Cancelar

**EXTRAYENDO TEXTO:**
- OCR/extracción en progreso
- **Progreso:** n de m documentos
- **Visual:** Badge azul animado, icono documento, barra de progreso
- **Acción disponible:** Cancelar

**INDEXANDO:**
- Creando índices de búsqueda vectorial
- **Visual:** Badge azul animado, icono base de datos
- **Acción disponible:** Cancelar

**ANALIZANDO CATEGORÍAS:**
- 8 nodos de extracción paralela ejecutándose
- **Progreso:** n de 8 categorías completas
- **Visual:** Badge azul animado, icono IA, barra de progreso, lista de categorías completas
- **Acción disponible:** Cancelar

**CONSOLIDANDO:**
- Merge de resultados, detección de conflictos
- **Visual:** Badge azul animado, icono engranajes
- **Acción disponible:** Ver parcial (si falla)

**ANALIZADO:**
- Extracción completa, pendiente de validación humana
- **Visual:** Badge {components.badge.status.analyzed}, icono advertencia
- **Acciones disponibles:**
  - Ver resultados
  - Re-analizar
  - Duplicar
  - Eliminar

**VALIDADO:**
- Usuario revisó categorías críticas, resolvió conflictos, marcó como validado
- **Propiedades:**
  - Validado por: usuario
  - Validado en: timestamp
- **Visual:** Badge {components.badge.status.validated}, icono check verde
- **Acciones disponibles:**
  - Ver resultados
  - Re-analizar
  - Duplicar
  - Eliminar

**CANCELADO:**
- Usuario canceló durante el procesamiento
- **Visual:** Badge {components.badge.status.cancelled}, icono X
- **Acciones disponibles:**
  - Re-analizar
  - Eliminar

**ERROR:**
- Fallo irrecuperable en el análisis
- **Propiedades:**
  - Mensaje de error
  - Stack trace (para debugging)
- **Visual:** Badge {components.badge.status.error}, icono 🔴
- **Acciones disponibles:**
  - Ver error
  - Reintentar
  - Eliminar

### 5.4. Transiciones y Validaciones

**Transición a Validado (requiere):**
- ✅ Las 3 categorías críticas están en estado "Revisada"
- ✅ No hay conflictos sin resolver
- ✅ Confirmación explícita del usuario

**Transición a Modificado (desde cualquier campo):**
- Modal de edición → Guardar → registra cambio → marca categoría como "Sin revisar"

**Resolución de conflicto:**
- Modal con radio buttons → Confirmar → campo pasa a "Resuelto" (sub-estado de Extraído)

**Marcar categoría como Revisada:**
- Click en botón → registra timestamp y usuario → estado "Revisada"
- Si usuario edita cualquier campo → vuelve a "Sin revisar"

---

## 6. Interaction Primitives

### 6.1. Click

**Elementos clickables:**
- Botones, links, cards clickables, items de lista, radio buttons, checkboxes
- **Visual hover:** Cursor pointer, cambio de color/sombra
- **Visual active:** Escala 98%, feedback táctil
- **Feedback:** Acción inmediata o transición suave (no delay)

**Prevención de doble-click:**
- Botones de formulario se deshabilitan después del primer click
- Spinner reemplaza texto mientras se procesa

### 6.2. Hover

**Propósito:** Descubrimiento de acciones, preview, tooltips

**Comportamientos:**
- **Botones:** Cambio de background
- **Cards:** Elevación de shadow
- **Links:** Underline
- **Campos con cita:** Preview de cita en tooltip
- **Badges:** Tooltip con explicación del estado

**Timing:** Hover inmediato en elementos interactivos, 500ms delay para tooltips

### 6.3. Focus

**Keyboard navigation:**
- Tab recorre todos los elementos interactivos en orden lógico
- Shift+Tab retrocede
- Enter activa el elemento focuseado (botón, link)
- Space activa checkboxes, radio buttons
- Escape cierra modales

**Visual focus:**
- Outline azul 2px ({colors.primary_blue}) alrededor del elemento
- Nunca quitar outline (accesibilidad crítica)
- Focus trap en modales (Tab no sale del modal)

### 6.4. Drag and Drop

**Zona de upload:**
- **Drag enter:** Borde sólido azul, fondo azul claro
- **Drag over:** Mantiene estado, cursor "copy"
- **Drop:** Animación de feedback, validación inmediata
- **Drag leave:** Vuelve a estado normal

**Validación en drop:**
- Archivos válidos → agregan a lista
- Archivos inválidos → mensaje de error individual

### 6.5. Expand / Collapse

**Categorías (acordeones):**
- **Trigger:** Click en header completo (no solo icono)
- **Visual:** Icono ▼ rota a ▲, transición suave 200ms
- **Contenido:** Slide down/up con fade, easing ease-out
- **Estado persistido:** Expansiones se guardan en session (usuario vuelve y está como lo dejó)

**Comportamiento:**
- Solo una categoría expandida a la vez: NO (permite comparar múltiples)
- Expandir/colapsar no requiere roundtrip al servidor

### 6.6. Scroll

**Dashboard (lista de análisis):**
- Scroll vertical dentro del contenedor principal
- Scroll infinito: NO (paginación explícita)

**Detalle (categorías):**
- Panel izquierdo (categorías) scrollea independiente
- Panel derecho (PDF) scrollea independiente
- Scroll horizontal: NO (responsive trunca texto con ellipsis)

**Scroll programático:**
- Al hacer "Ver fuente" → scroll del PDF a la página correcta, suave
- Al detectar campo crítico → scroll de categoría a ese campo

### 6.7. Animaciones

**Principio:** Animaciones sutiles, funcionales, nunca decorativas

**Transiciones estándar:**
- Fade in/out: 200ms
- Slide in/out: 300ms
- Scale: 150ms
- Color change: 150ms

**Animaciones de estado:**
- Loading spinner: rotación continua
- Badge "Analizando": pulso suave 2s loop
- Drag over: escala 102%, transición 200ms

**Reducción de movimiento:**
- Respetar `prefers-reduced-motion`
- Si activo: todas las animaciones → instant (0ms)

---

## 7. Accessibility Floor

### 7.1. Navegación por Teclado

**Requisitos WCAG 2.1 AA:**

✅ **Tab order lógico:**
- Sidebar → Header → Contenido principal → Footer
- Dentro de formularios: orden visual == orden de tabulación
- Focus visible siempre (outline 2px {colors.primary_blue})

✅ **Atajos de teclado (futuros):**
- `/` → Focus en buscador
- `Escape` → Cerrar modal/dropdown
- `Enter` → Activar botón focuseado
- `Space` → Toggle checkbox/radio

✅ **Skip links:**
- "Saltar al contenido principal" (visible en focus)

### 7.2. Screen Readers

**Estructura semántica:**
- HTML5 landmarks: `<header>`, `<nav>`, `<main>`, `<aside>`, `<footer>`
- Headings jerárquicos: H1 (página) → H2 (secciones) → H3 (subsecciones)
- Lists para navegación y cards

**ARIA labels:**
```html
<!-- Botones con iconos -->
<button aria-label="Cerrar modal">×</button>

<!-- Estados dinámicos -->
<div role="status" aria-live="polite">
  Analizando categorías (5 de 8)
</div>

<!-- Badges -->
<span class="badge" aria-label="Estado: Validado">Validado</span>

<!-- Progreso -->
<div role="progressbar" aria-valuenow="5" aria-valuemin="0" 
     aria-valuemax="8" aria-label="Analizando categorías">
  5 de 8
</div>
```

**Anuncios de cambios:**
- `aria-live="polite"` para progreso
- `aria-live="assertive"` para errores
- Mensajes de éxito/error tienen role="status" o role="alert"

### 7.3. Contraste y Legibilidad

**Requisito WCAG AA:**
- Texto normal (< 18pt): contraste mínimo 4.5:1
- Texto grande (≥ 18pt o ≥ 14pt bold): contraste mínimo 3:1
- UI components y gráficos: contraste mínimo 3:1

**Paleta validada:**
- {colors.gray_900} sobre {colors.background}: 15.7:1 ✅
- {colors.primary_blue} sobre blanco: 6.2:1 ✅
- {colors.error} sobre {colors.error_light}: 8.1:1 ✅

**Texto sobre fondos de estado:**
- Conflicto: {colors.error} sobre {colors.error_light}
- Advertencia: {colors.warning} sobre {colors.warning_light}
- Éxito: {colors.success} sobre {colors.success_light}

### 7.4. Tamaño de Targets

**Mínimo WCAG AA:** 44×44px para touch targets

**Implementación:**
- Botones: min 40px altura ({components.button.height_md})
- Iconos clickables: min 44×44px área de click (padding visual)
- Checkboxes/radios: 20×20px visual, 44×44px área de click
- Links en texto: min 16px altura línea

### 7.5. Formularios Accesibles

**Labels:**
- Todo input tiene `<label>` asociado (for/id)
- Placeholder NO reemplaza label
- Labels visibles siempre

**Errores:**
- `aria-describedby` apunta al mensaje de error
- `aria-invalid="true"` en inputs con error
- Mensajes de error con iconografía + texto (no solo color)

**Grupos de campos:**
- `<fieldset>` + `<legend>` para grupos relacionados
- Radio buttons de conflictos: fieldset con legend "Seleccioná el valor correcto"

---

## 8. Key Flows

### 8.1. Análisis Nuevo (Flujo Feliz)

**Protagonista:** María, ejecutiva comercial de PIConsulting, recibe un pliego de 40 páginas de la Municipalidad de Rosario.

**Paso 1: Subir archivos**

1. María abre CedIA, hace click en "Analizar nuevo pliego" en el sidebar
2. Sistema muestra wizard paso 1/3: "Subir archivos"
3. María arrastra `pliego-rosario-2026.pdf` desde su escritorio a la zona de drop
4. Zona de drop cambia de borde punteado gris a borde azul sólido durante el drag
5. Al soltar, el archivo aparece en la lista con spinner "Validando..."
6. 2 segundos después: checkmark verde "✓ Válido — 40 páginas, 12 MB"
7. María agrega un segundo archivo `anexo-formularios.pdf` con el botón "Seleccionar archivos"
8. Segundo archivo valida: "✓ Válido — 8 páginas, 2 MB"
9. Botón "Siguiente" se habilita (era gris, pasa a azul primario)
10. María hace click en "Siguiente"

**Paso 2: Designar principal**

11. Sistema detecta 2 archivos → muestra paso 2/3: "Documento principal"
12. Lista de radio buttons, `pliego-rosario-2026.pdf` pre-seleccionado
13. María confirma (ya estaba correcto), hace click en "Siguiente"

**Paso 3: Confirmar**

14. Sistema muestra resumen:
    - Documento principal: pliego-rosario-2026.pdf (12 MB, 40 págs)
    - Anexos: anexo-formularios.pdf (2 MB, 8 págs)
    - Total: 2 archivos, 14 MB, 48 páginas
    - Tiempo estimado: 3-5 minutos
15. María hace click en "Iniciar análisis"

**Progreso:**

16. Transición a pantalla de progreso
17. Spinner animado + "Extrayendo texto (1 de 2 documentos)"
18. Barra de progreso al 50%
19. María navega a otra pestaña para responder un email
20. 30 segundos después, badge "Analizando" → "Indexando"
21. 10 segundos después → "Analizando categorías (2 de 8 completas)"
22. Lista de categorías completas: "Plazos clave, Garantías"
23. María vuelve a la pestaña, ve "Analizando categorías (6 de 8)"
24. 2 minutos después → "¡Análisis completado!"
25. Auto-redirect en 2 segundos a pantalla de Detalle

**Resultado:**

26. Sistema muestra pantalla de Detalle con 8 categorías colapsadas
27. Tres categorías destacadas con ⚠️ y badge "⭐ CRÍTICA":
    - Plazos clave: 6/7 extraídos, 1 no encontrado
    - Garantías: 3/3 extraídos, 1 en conflicto
    - Causales de rechazo: 8/8 extraídos
28. Panel derecho muestra preview del PDF
29. Footer con botón "Validar análisis" deshabilitado (tooltip: "Revisá las 3 categorías críticas")

**Tiempo total:** 3 minutos desde subir hasta ver resultados.

---

### 8.2. Revisión de Campo (Resolver Conflicto)

**Protagonista:** María revisa la categoría Garantías en el análisis recién completado.

**Contexto:** Campo "Monto garantía de mantenimiento de oferta" tiene conflicto.

**Flujo:**

1. María hace click en card "⚠️ Garantías ⭐ CRÍTICA"
2. Card se expande con animación slide-down (300ms)
3. Campos se muestran ordenados por severidad:
   - **Primero:** "❌ Monto garantía mantenimiento [EN CONFLICTO]"
   - Después: campos extraídos con confianza Alta
4. María lee el campo en conflicto:
   ```
   Valor 1 (pliego-rosario-2026.pdf, pág 9):
   "5% del presupuesto oficial"
   Confianza: Alta

   Valor 2 (anexo-formularios.pdf, pág 2):
   "3% del monto ofertado"
   Confianza: Media
   ```
5. María hace click en "Resolver conflicto"
6. Modal aparece con fade-in (200ms):
   - Título: "Resolver conflicto"
   - Dos radio buttons con los valores completos
   - Botón "Ver en documento" bajo cada valor
7. María hace click en "Ver en documento" del Valor 1
8. Panel derecho del PDF navega a página 9 con scroll suave
9. Texto "5% del presupuesto oficial" se resalta en amarillo
10. María confirma que ese es el correcto, cierra el modal, vuelve al modal de conflicto
11. Selecciona radio button del Valor 1
12. Hace click en "Confirmar"
13. Modal se cierra con fade-out (200ms)
14. Campo actualiza a:
    ```
    ✓ Monto garantía mantenimiento [CONFIANZA: ALTA]
    "5% del presupuesto oficial"
    📄 Fuente: pliego-rosario-2026.pdf, pág. 9
    ```
15. Badge del card de Garantías actualiza: "3/3 extraídos" (sin conflictos)
16. Categoría sigue "Sin revisar" hasta que María marque explícitamente
17. María revisa los otros dos campos (ambos confianza Alta)
18. Hace click en "Marcar categoría como revisada"
19. Card de Garantías cambia:
    - Borde gris → verde
    - Icono ⚠️ → ✓
    - Badge "Sin revisar" → "Revisada el 31/7 a las 10:45 por agostorres04"

**Resultado:** Una categoría crítica menos por revisar. Botón "Validar" sigue deshabilitado (faltan Plazos y Causales).

---

### 8.3. Agregar Campo Manualmente

**Protagonista:** María encuentra que "Plazo de consultas" no fue extraído.

**Flujo:**

1. María expande categoría "⚠️ Plazos clave"
2. Ve campo "⚠️ Consultas [NO ENCONTRADO]"
3. Lee mensaje: "No se encontró información sobre el plazo para consultas"
4. María sabe que está en el pliego, hace click en "Agregar manualmente"
5. Modal aparece:
   - Título: "Agregar manualmente"
   - Input vacío para el valor
   - Textarea para justificación (opcional)
   - Sin referencia a "valor original del sistema" (porque no hay)
6. María escribe en el input: "Hasta 5 días hábiles antes de la apertura"
7. En justificación: "Artículo 12 del pliego"
8. Hace click en "Guardar"
9. Modal se cierra
10. Campo actualiza a:
    ```
    ✏️ Consultas [MODIFICADO]
    
    Valor actual:
    "Hasta 5 días hábiles antes de la apertura"
    
    Valor original del sistema:
    (No encontrado)
    
    Modificado por agostorres04 el 31/7 a las 10:52
    Justificación: "Artículo 12 del pliego"
    ```
11. Categoría "Plazos clave" vuelve a estado "Sin revisar" (porque hubo modificación)
12. María revisa los otros plazos, marca la categoría como revisada

---

### 8.4. Validación (Happy Path)

**Protagonista:** María terminó de revisar las 3 categorías críticas y resolvió todos los conflictos.

**Precondiciones:**
- ✅ Plazos clave: Revisada
- ✅ Garantías: Revisada
- ✅ Causales de rechazo: Revisada
- ✅ 0 conflictos sin resolver

**Flujo:**

1. María hace scroll al footer de la pantalla de Detalle
2. Botón "Validar análisis" está habilitado (verde primario)
3. María hace click en "Validar análisis"
4. Modal de confirmación aparece:
   ```
   ¿Estás seguro que querés validar este análisis?

   Revisaste las 3 categorías críticas:
   ✓ Plazos clave
   ✓ Garantías
   ✓ Causales de rechazo

   No quedan conflictos sin resolver

   Al validar, este análisis quedará marcado como listo
   para usar en la evaluación de la licitación
   ```
5. María hace click en "Validar"
6. Modal se cierra
7. Header del análisis actualiza:
   - Badge "Analizado" → "Validado"
   - Color amarillo → verde
   - Agrega: "Validado por agostorres04 el 31/7 a las 11:05"
8. Toast de éxito aparece: "✓ Análisis validado correctamente"
9. Botón "Validar" desaparece del footer (ya está validado)

**Tiempo total desde abrir el análisis:** ~10 minutos.

---

### 8.5. Detección de Duplicado

**Protagonista:** Carlos, otro ejecutivo, intenta analizar el mismo pliego que María ya analizó.

**Flujo:**

1. Carlos sube `pliego-rosario-2026.pdf`
2. Sistema valida archivo (checkmark verde)
3. Carlos hace click en "Siguiente" → "Iniciar análisis"
4. Sistema calcula hash del archivo antes de procesar
5. Detecta que hash coincide con análisis existente (el de María)
6. Antes de iniciar extracción, sistema muestra modal:
   ```
   Este archivo ya fue analizado

   pliego-rosario-2026.pdf
   Analizado por agostorres04 el 25/7/2026
   Estado: Validado

   ¿Qué querés hacer?

   [Ver análisis existente]  [Re-analizar]  [Cancelar]
   ```
7. Carlos hace click en "Ver análisis existente"
8. Sistema redirige a la pantalla de Detalle del análisis de María
9. Carlos ve el análisis completo, puede hacer sus propias correcciones
10. Si Carlos modifica algo, queda registrado: "Modificado por carlos.lopez"

**Alternativa: Re-analizar**
- Si Carlos elige "Re-analizar", sistema crea nueva versión
- Link en header: "Versión 2 de 2 | Ver versiones anteriores"
- Sistema detecta correcciones previas, pregunta si quiere aplicarlas campo por campo

---

### 8.6. Re-análisis con Correcciones Previas

**Protagonista:** María quiere re-analizar el pliego después de 2 semanas porque hubo una circular aclaratoria.

**Contexto:** Análisis original tiene 3 campos corregidos manualmente.

**Flujo:**

1. María abre el análisis original (validado)
2. Hace click en botón "Re-analizar" en el header
3. Modal de confirmación:
   ```
   ¿Re-analizar este pliego?

   Se creará una nueva versión del análisis.
   El análisis actual no se modificará.

   Este análisis tiene 3 correcciones manuales:
   • Plazos clave: Consultas
   • Garantías: Monto garantía
   • Objeto: Lugar de entrega

   ¿Querés aplicar estas correcciones al nuevo análisis?

   [ ] Sí, copiar mis correcciones
   
   [Cancelar]  [Re-analizar]
   ```
4. María marca el checkbox "Sí, copiar mis correcciones"
5. Hace click en "Re-analizar"
6. Sistema muestra paso 1: "Subir archivos"
7. María agrega el pliego original + la circular aclaratoria
8. Completa wizard (designar principal, confirmar)
9. Análisis comienza, progreso igual que flujo 8.1
10. Cuando termina, sistema:
    - Crea nueva versión (Versión 2)
    - Copia los 3 campos corregidos manualmente del análisis original
    - Los marca como "COPIADO DE VERSIÓN ANTERIOR"
    - Detecta nuevos conflictos (circular vs pliego)
11. María ve Detalle de versión 2:
    - Header: "Versión 2 de 2 | Ver versión anterior"
    - Campos copiados tienen badge "COPIADO" + link "Ver origen"
    - Nuevos conflictos (de la circular) requieren resolución

---

### 8.7. Cancelar Análisis en Progreso

**Protagonista:** María subió un pliego equivocado y quiere cancelar.

**Flujo:**

1. María inicia análisis de un archivo
2. Durante la etapa "Extrayendo texto (1 de 1)", se da cuenta del error
3. Hace click en botón "Cancelar análisis" (rojo, abajo del progreso)
4. Modal de confirmación:
   ```
   ¿Cancelar el análisis en curso?

   El análisis se detendrá y no podrás recuperar
   el progreso actual

   [Volver]  [Cancelar análisis]
   ```
5. María confirma "Cancelar análisis"
6. Sistema envía señal de cancelación al backend
7. Progreso se detiene
8. Badge cambia a "Cancelado"
9. Mensaje: "Análisis cancelado. Podés eliminarlo del historial"
10. María vuelve al Dashboard
11. Análisis cancelado aparece con badge "Cancelado" y botón "Eliminar"

---

### 8.8. Manejo de Error en Categoría

**Protagonista:** Un análisis tiene error en la categoría "Criterios de evaluación" (bug en el nodo).

**Flujo:**

1. Sistema completa 7 de 8 categorías exitosamente
2. Nodo "Criterios de evaluación" falla (excepción no capturada)
3. Sistema **NO** marca el análisis completo como Error
4. Marca solo esa categoría como "Error al analizar"
5. Sistema consolida las otras 7 categorías y pasa a estado "Analizado"
6. María ve Detalle:
   - 7 categorías con datos
   - 1 categoría con error:
     ```
     🔴 Criterios de evaluación [ERROR]

     Error al analizar esta categoría.
     Podés reintentar o agregar los datos manualmente

     [Reintentar]  [Agregar manualmente]
     ```
7. María hace click en "Reintentar"
8. Sistema re-ejecuta solo ese nodo
9. Si falla de nuevo después de 2 reintentos, sistema sugiere:
   ```
   El sistema no pudo analizar esta categoría.
   Agregá los criterios manualmente
   ```
10. María hace click en "Agregar manualmente"
11. Sistema abre formulario para ingresar campos de esa categoría
12. María completa, guarda
13. Categoría pasa a "Modificado" (todos los campos son manuales)

**Resultado:** No se pierde el análisis completo por fallo de una categoría.

---

## 9. Responsive & Platform

### 9.1. Breakpoints

**Definición:**

- **Desktop (primario):** ≥1366px — Layout completo de 2 columnas
- **Tablet landscape:** 1024px - 1365px — Layout de 2 columnas, visor PDF colapsable por default
- **Tablet portrait:** 768px - 1023px — Layout de 1 columna, visor PDF en modal full-screen
- **Mobile:** <768px — Solo consulta, sin edición

### 9.2. Comportamiento por Breakpoint

**Desktop (≥1366px):**
- Sidebar: 240px fijo, siempre visible
- Detalle: 2 columnas (60% categorías / 40% PDF)
- Visor PDF: visible por default
- Modales: max-width 600px, centrados

**Tablet landscape (1024-1365px):**
- Sidebar: 240px fijo o colapsable a 64px (toggle)
- Detalle: 2 columnas (70% categorías / 30% PDF)
- Visor PDF: colapsado por default, botón "Ver PDF" lo expande
- Modales: max-width 500px

**Tablet portrait (768-1023px):**
- Sidebar: Colapsable con hamburger menu
- Detalle: 1 columna (categorías)
- Visor PDF: Botón "Ver PDF" abre modal full-screen sobre las categorías
- Modales: max-width 90vw

**Mobile (<768px):**
- Solo consulta (read-only)
- Sidebar: Hamburger menu
- Dashboard: Cards apilados verticalmente
- Detalle: Solo categorías, visor PDF abre en nueva pestaña (navegador maneja el PDF)
- Wizard de análisis nuevo: NO disponible (mensaje: "Usá una computadora para analizar pliegos")
- Edición de campos: NO disponible

### 9.3. Touch Targets en Mobile/Tablet

**Requisitos:**
- Mínimo 48×48px para todos los elementos interactivos
- Separación mínima 8px entre targets
- Botones de acciones: altura mínima 48px
- Links en texto: padding vertical adicional para alcanzar 48px de área táctil

### 9.4. Gestos Táctiles (Tablet)

**Swipe:**
- Swipe horizontal en card de análisis → revelar acciones (Eliminar, Duplicar)
- Swipe en PDF → página anterior/siguiente

**Pinch to zoom:**
- En visor PDF (solo en tablets/mobile)
- Desktop usa botones +/-

**Long press:**
- En card de análisis → menú contextual
- En campo → copiar valor

### 9.5. Orientación (Tablet)

**Landscape (recomendado):**
- Layout de 2 columnas como desktop reducido

**Portrait:**
- Layout de 1 columna
- Visor PDF en modal

**Mensaje al rotar a portrait durante revisión:**
```
💡 Girá tu dispositivo a horizontal para ver 
   el PDF y las categorías al mismo tiempo
```

---

## 10. Principios de Implementación

### 10.1. Progressive Enhancement

**Capa 1 (HTML + CSS básico):**
- Estructura semántica
- Formularios funcionales
- Sin JavaScript: formularios se envían, navegación funciona

**Capa 2 (+ JavaScript):**
- Validación cliente-side
- Interacciones enriquecidas (drag & drop, expand/collapse)
- Modales, tooltips

**Capa 3 (+ API moderna):**
- Progreso en tiempo real (WebSockets)
- Resaltado de PDF inline
- Auto-save de expansiones

### 10.2. Performance Budget

**Métricas objetivo:**
- **FCP (First Contentful Paint):** <1.5s
- **LCP (Largest Contentful Paint):** <2.5s
- **TTI (Time to Interactive):** <3.5s
- **CLS (Cumulative Layout Shift):** <0.1

**Estrategias:**
- Lazy loading de PDF viewer
- Skeleton loading para listas
- Debounce en búsqueda (300ms)
- Virtualización de listas largas (>50 items)

### 10.3. Offline / Network Resilience

**Degradación graciosa:**
- Análisis en progreso: continúa en backend, polling periódico para actualizar UI
- Pérdida de conexión durante revisión: cambios locales se guardan, sync cuando vuelve conexión
- Error de red: Retry automático 3 veces, luego mensaje al usuario

**Feedback de conectividad:**
- Banner discreto arriba: "Sin conexión — Tus cambios se guardarán cuando vuelva internet"

---

## 11. Glosario de Términos de Interacción

**CTA (Call to Action):** Botón primario que guía al usuario a la acción más importante del contexto

**Focus trap:** Técnica de accesibilidad que restringe la navegación por teclado dentro de un modal

**Skeleton loading:** Placeholders animados que muestran la estructura del contenido mientras carga

**Toast:** Notificación temporal que aparece y desaparece automáticamente

**Debounce:** Técnica que espera a que el usuario termine de escribir antes de ejecutar una búsqueda

**Lazy loading:** Carga diferida de contenido hasta que el usuario lo necesita

**Progressive disclosure:** Mostrar solo lo necesario inicialmente, revelar detalles bajo demanda

**Optimistic UI:** Actualizar la UI inmediatamente asumiendo éxito, revertir si falla

---

**Fin del documento EXPERIENCE.md**

Este contrato de comportamiento e interacción debe leerse junto con DESIGN.md (especificaciones visuales) para la implementación completa del sistema CedIA.
