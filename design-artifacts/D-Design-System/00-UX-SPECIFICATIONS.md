# Especificaciones UX/UI - Sistema de Análisis de Pliegos CedIA

**Proyecto:** licitaciones-pi  
**Versión:** 1.0  
**Fecha:** 2026-07-31  
**Basado en:** PRD v2.0 (2026-07-29)  
**Librería de iconos:** Lucide React (`lucide-react`)

> **Nota sobre iconos:** Este documento usa nombres de componentes de Lucide React entre corchetes (ej: `[FileText]`, `[AlertTriangle]`) para especificar iconos. Ver sección 6.3 para mapeo completo.

---

## Índice

1. [Visión General del Diseño](#1-visión-general-del-diseño)
2. [Arquitectura de Información](#2-arquitectura-de-información)
3. [Sistema de Navegación](#3-sistema-de-navegación)
4. [Pantallas y Flujos](#4-pantallas-y-flujos)
5. [Componentes de Diseño](#5-componentes-de-diseño)
6. [Sistema Visual y Tokens](#6-sistema-visual-y-tokens)
7. [Estados y Feedback](#7-estados-y-feedback)
8. [Responsive y Breakpoints](#8-responsive-y-breakpoints)

---

## 1. Visión General del Diseño

### 1.1. Principios de Diseño UX

**Transparencia Radical**
- Todo valor extraído muestra su fuente verificable
- Los conflictos se exponen, nunca se ocultan
- El usuario siempre sabe qué revisó y qué falta

**Guía por Severidad**
- La atención va primero a lo crítico (conflictos, campos no encontrados)
- Tres categorías críticas (Plazos, Garantías, Causales) reciben tratamiento diferenciado
- Los campos se ordenan por costo de equivocarse

**Validación como Responsabilidad**
- No se puede validar sin revisar las categorías críticas
- Toda edición marca la categoría como "Sin revisar"
- Registro explícito de quién validó qué y cuándo

**Claridad sobre Precisión**
- Confianza como acción (Alta/Media/Baja) no como porcentaje
- Estados honestos: Extraído, No encontrado, No aplica, En conflicto
- Mensajes de error que explican qué pasó y qué hacer

### 1.2. Referencia Visual

El diseño toma inspiración de las capturas proporcionadas (Dashboard limpio con navegación lateral, cards para análisis, vistas detalladas) pero **NO replica exactamente** esas interfaces. Adaptamos:

- Navegación lateral izquierda consistente
- Layout de dos columnas para resultados + visor PDF
- Cards con estados visuales claros
- Tipografía clara y espaciado generoso
- Estética profesional, minimalista, enfocada en datos

---

## 2. Arquitectura de Información

### 2.1. Estructura de Navegación

```
CedIA
├── Dashboard (Historial)
│   └── Ver análisis existente → Detalle del análisis
├── Analizar Nuevo Pliego
│   ├── Subir archivos
│   ├── Designar principal
│   ├── Confirmación
│   ├── Progreso
│   └── Resultados → Detalle del análisis
└── [Usuario]
    └── Cerrar sesión
```

### 2.2. Jerarquía de Información

**Nivel 1 - Global**
- Navegación principal
- Nombre del sistema (CedIA)
- Usuario activo

**Nivel 2 - Pantalla**
- Título de la pantalla
- Acciones principales
- Filtros/búsqueda (donde aplique)

**Nivel 3 - Contenido**
- Listados, cards, tablas
- Resúmenes y métricas
- Estados y badges

**Nivel 4 - Detalle**
- Información expandida
- Modales y popovers
- Tooltips

---

## 3. Sistema de Navegación

### 3.1. Barra Lateral Izquierda (Sidebar)

**Dimensiones:**
- Ancho: 240px (colapsable a 64px con solo iconos)
- Altura: 100vh
- Posición: Fixed

**Contenido (de arriba hacia abajo):**

```
┌─────────────────────┐
│  [Logo] CedIA       │  ← Branding (40px alto)
├─────────────────────┤
│                     │
│  📊 Dashboard       │  ← Item activo (fondo resaltado)
│  ✨ Analizar Pliego│
│                     │
│  ... (proximamente) │  ← Radar, Chat IA, etc
│                     │
├─────────────────────┤  ← Separador
│  [Avatar]           │
│  agostorres04       │  ← Usuario
│  ⚙️ Cerrar sesión   │
└─────────────────────┘
```

**Estados de los items:**
- Normal: texto gris, fondo transparente
- Hover: fondo gris claro, cursor pointer
- Activo: fondo azul suave, texto azul oscuro, borde izquierdo azul (4px)

### 3.2. Barra Superior (Top Bar) - Opcional

En páginas de contenido, opcional:

```
┌────────────────────────────────────────────────┐
│ [← Volver] | Título de la Página | [Acciones] │
└────────────────────────────────────────────────┘
```

Altura: 64px
- Botón volver (cuando aplica)
- Título centrado o alineado izquierda
- Acciones contextuales a la derecha

---

## 4. Pantallas y Flujos

### 4.1. LOGIN

**Layout:**
- Centrado vertical y horizontalmente
- Card de 400px ancho máximo
- Fondo con gradiente suave o color corporativo

**Contenido:**

```
┌──────────────────────┐
│   [Logo CedIA]    │
│                      │
│  Análisis de pliegos │  ← Tagline
│                      │
│  [Email]            │  ← Input
│  [Contraseña]       │  ← Input password
│  [Recordarme] □     │  ← Checkbox
│                      │
│  [Iniciar sesión]   │  ← Botón primario
│                      │
│  ¿Olvidaste tu...?  │  ← Link (post-MVP)
└──────────────────────┘
```

**Validaciones:**
- Email: formato válido
- Contraseña: mínimo 8 caracteres
- Mensajes de error debajo de cada campo
- Error de credenciales: banner rojo arriba del formulario

**Estados:**
- Cargando: botón con spinner, inputs deshabilitados
- Error: bordes rojos, mensaje de error visible
- Éxito: transición al Dashboard

---

### 4.2. DASHBOARD (HISTORIAL)

**Layout: Contenedor principal con sidebar + contenido**

```
┌─────────┬────────────────────────────────────────┐
│         │  Dashboard                             │
│         │  ┌───────────────┐ ┌────────────────┐  │
│ Sidebar │  │ Buscar...     │ │ [+ Nuevo]     │  │
│         │  └───────────────┘ └────────────────┘  │
│         │  [Filtros: Fecha ▾] [Estado ▾]         │
│         │                                         │
│         │  ┌──────────────────────────────────┐  │
│         │  │ 📄 Pliego Mantenimiento IT       │  │
│         │  │    Ministerio de Hacienda        │  │
│         │  │    25/7/2026 • 8/8 revisadas • ✓ │  │
│         │  │    [Ver análisis] [⋮ Más]        │  │
│         │  └──────────────────────────────────┘  │
│         │                                         │
│         │  [más cards...]                        │
│         │                                         │
│         │  [Paginación 1 2 3 ... 10]            │
└─────────┴────────────────────────────────────────┘
```

**Sección Superior (Header):**
- Título: "Dashboard" (H1)
- Buscador: input con icono de lupa, placeholder "Buscar por pliego u organismo..."
- Botón primario: "+ Analizar nuevo pliego" (acción principal)

**Filtros (debajo del header):**
- Fecha: dropdown con opciones (Última semana, Último mes, Últimos 3 meses, Personalizado)
- Estado: dropdown con opciones (Todos, En cola, Analizando, Analizado, Validado, Error, Cancelado)
- Se aplican automáticamente al seleccionar

**Tabla/Cards de Análisis:**

Cada análisis se muestra como un card horizontal:

```
┌────────────────────────────────────────────────────────┐
│ 📄 [Nombre del Pliego]                    [Badge Estado]│
│    [Organismo convocante]                               │
│    📅 25/7/2026  •  � 5/8 revisadas  •  📄 35 págs    │
│    Creado por: agostorres04                            │
│                                                         │
│    [Ver análisis]  [Re-analizar]  [⋮ Más]             │
└────────────────────────────────────────────────────────┘
```

**Columnas de información:**
1. **Nombre:** Nombre del pliego (truncado a 60 caracteres)
2. **Organismo:** Nombre del organismo
3. **Fecha:** Fecha del análisis
4. **Progreso:** Categorías revisadas (ej: "5/8 revisadas") o estado general
5. **Estado:** Badge con color según estado
6. **Acciones:** Botones de acción

**Estados Visuales (Badges):**
- **En cola:** Gris claro, icono reloj
- **Analizando:** Azul animado, icono spinner
- **Analizado:** Amarillo, icono advertencia (falta validar)
- **Validado:** Verde, icono check
- **Error:** Rojo, icono X
- **Cancelado:** Gris, icono cancelar

**Menú de Acciones (⋮):**
- Ver análisis
- Re-analizar (crear nueva versión)
- Ver versiones anteriores (si hay)
- Eliminar (con confirmación)

**Estado Vacío:**
Si no hay análisis:
```
┌─────────────────────────────────┐
│         [Icono documento]       │
│                                 │
│    No hay análisis todavía     │
│                                 │
│    Comenzá analizando tu       │
│    primer pliego               │
│                                 │
│    [Analizar nuevo pliego]     │
└─────────────────────────────────┘
```

**Paginación:**
- Máximo 20 items por página
- Navegación: < 1 2 3 ... 10 >
- Mostrar: "Mostrando 1-20 de 157 análisis"

---

### 4.3. ANALIZAR NUEVO PLIEGO - Paso 1: Subir Archivos

**Layout:**

```
┌─────────┬──────────────────────────────────────────┐
│         │  Analizar nuevo pliego                   │
│         │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│ Sidebar │  Paso 1 de 3: Subir archivos            │
│         │                                           │
│         │  ┌─────────────────────────────────────┐ │
│         │  │                                     │ │
│         │  │     [Icono subir]                   │ │
│         │  │                                     │ │
│         │  │  Arrastrá archivos acá o           │ │
│         │  │  [Seleccionar archivos]            │ │
│         │  │                                     │ │
│         │  │  Solo PDF • Máx 10 archivos        │ │
│         │  │  Máx 50 MB por archivo             │ │
│         │  └─────────────────────────────────────┘ │
│         │                                           │
│         │  [Archivos seleccionados:]               │
│         │  ┌─────────────────────────────────────┐ │
│         │  │ 📄 pliego-principal.pdf  25 MB      │ │
│         │  │    [✓ Válido]                 [X]   │ │
│         │  └─────────────────────────────────────┘ │
│         │  ┌─────────────────────────────────────┐ │
│         │  │ 📄 anexo-tecnico.pdf  12 MB         │ │
│         │  │    [✓ Válido]                 [X]   │ │
│         │  └─────────────────────────────────────┘ │
│         │                                           │
│         │  [Cancelar]        [Siguiente →]        │
└─────────┴──────────────────────────────────────────┘
```

**Indicador de Progreso (top):**
```
Paso 1: Subir archivos  →  Paso 2: Documento principal  →  Paso 3: Confirmar
   [●━━━━━━]                  [○━━━━━━]                      [○━━━━━━]
```

**Zona de subida (Drag & Drop):**
- Borde punteado, fondo gris muy claro
- Hover: borde azul, fondo azul muy claro
- Dragging over: animación suave
- Altura: 200px mínimo

**Botón "Seleccionar archivos":**
- Abre file picker del sistema
- Filtro: solo archivos .pdf
- Multi-selección habilitada

**Lista de Archivos Seleccionados:**

Cada archivo se muestra como un item de lista:

```
┌──────────────────────────────────────────────┐
│ 📄 nombre-archivo.pdf            25.4 MB     │
│    [✓ Válido]  35 páginas            [X]     │
└──────────────────────────────────────────────┘
```

**Estados de validación en cliente (antes de subir):**

1. **Válido:** checkmark verde, texto "Válido"
2. **Error de formato:**
   ```
   ❌ Este archivo no es un PDF
   ```
3. **Archivo muy grande:**
   ```
   ⚠️ Este archivo pesa 68 MB. El máximo es 50 MB
      Probá comprimirlo o dividirlo
   ```
4. **Total excedido:**
   ```
   ⚠️ Los archivos suman 175 MB. El máximo total es 150 MB
      Quitá algunos archivos o analizalos en dos tandas
   ```
5. **Demasiados archivos:**
   ```
   ⚠️ Seleccionaste 12 archivos. El máximo es 10
   ```

**Botón "Siguiente":**
- Deshabilitado si:
  - No hay archivos seleccionados
  - Algún archivo tiene error de validación
  - Se exceden los límites
- Habilitado: azul primario
- Click: avanza al Paso 2

---

### 4.4. ANALIZAR NUEVO PLIEGO - Paso 2: Designar Documento Principal

**Solo se muestra si hay múltiples archivos. Si hay 1 solo, se salta automáticamente al Paso 3.**

```
┌─────────┬──────────────────────────────────────────┐
│         │  Analizar nuevo pliego                   │
│         │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│ Sidebar │  Paso 2 de 3: Documento principal       │
│         │                                           │
│         │  ¿Cuál es el pliego principal?           │
│         │  Los demás se considerarán anexos        │
│         │                                           │
│         │  ○ 📄 pliego-principal.pdf  (25 MB)      │
│         │  ○ 📄 anexo-tecnico.pdf  (12 MB)         │
│         │  ○ 📄 anexo-formularios.pdf  (3 MB)      │
│         │                                           │
│         │                                           │
│         │  [← Atrás]            [Siguiente →]     │
└─────────┴──────────────────────────────────────────┘
```

**Radio buttons:**
- Uno por archivo
- Pre-seleccionado: el primero en la lista
- Click en el nombre del archivo también selecciona

**Botón "Siguiente":**
- Siempre habilitado (al menos uno está seleccionado)
- Avanza al Paso 3

---

### 4.5. ANALIZAR NUEVO PLIEGO - Paso 3: Confirmar y Comenzar

```
┌─────────┬──────────────────────────────────────────┐
│         │  Analizar nuevo pliego                   │
│         │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│ Sidebar │  Paso 3 de 3: Confirmar                 │
│         │                                           │
│         │  Revisá los archivos antes de comenzar   │
│         │                                           │
│         │  📄 Documento principal:                 │
│         │     pliego-principal.pdf (25 MB, 35 págs)│
│         │                                           │
│         │  📎 Anexos:                              │
│         │     • anexo-tecnico.pdf (12 MB, 18 págs) │
│         │     • anexo-formularios.pdf (3 MB, 5 p.) │
│         │                                           │
│         │  Total: 3 archivos, 40 MB, 58 páginas   │
│         │  Tiempo estimado: 3-5 minutos            │
│         │                                           │
│         │  [← Atrás]       [Iniciar análisis]     │
└─────────┴──────────────────────────────────────────┘
```

**Resumen:**
- Documento principal destacado
- Listado de anexos
- Totales: archivos, peso, páginas
- Tiempo estimado según páginas totales (fórmula del PRD)

**Advertencia (si >100 páginas):**
```
⚠️ Este análisis tiene 150 páginas y puede demorar
   hasta 12 minutos según la extensión del documento
```

**Botón "Iniciar análisis":**
- Click: envía archivos al servidor
- Transición a pantalla de Progreso

---

### 4.6. PROGRESO DEL ANÁLISIS

**Aparece después de iniciar el análisis. Reemplaza el contenido principal.**

```
┌─────────┬──────────────────────────────────────────┐
│         │  Analizando pliego...                    │
│         │                                           │
│ Sidebar │  ┌─────────────────────────────────────┐ │
│         │  │                                     │ │
│         │  │      [Spinner animado]              │ │
│         │  │                                     │ │
│         │  │   Extrayendo texto                  │ │
│         │  │   (2 de 3 documentos)               │ │
│         │  │                                     │ │
│         │  │   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │ │
│         │  │                                     │ │
│         │  └─────────────────────────────────────┘ │
│         │                                           │
│         │  Podés navegar a otra pantalla y volver  │
│         │  Te notificaremos cuando termine         │
│         │                                           │
│         │  [Ver en historial]  [Cancelar análisis]│
└─────────┴──────────────────────────────────────────┘
```

**Etapas del progreso (según §7.5 del PRD):**

1. **En cola**
   - Icono: reloj
   - Texto: "Tu análisis está en cola, comenzará en breve"

2. **Extrayendo texto (n de m documentos)**
   - Icono: documento con lupa
   - Texto: "Extrayendo texto del documento 2 de 3"
   - Progreso: barra con n/m

3. **Indexando**
   - Icono: base de datos
   - Texto: "Indexando contenido para búsqueda"

4. **Analizando categorías (n de 8)**
   - Icono: cerebro/IA
   - Texto: "Analizando categorías (5 de 8 completas)"
   - Progreso: barra con n/8
   - Subtext: "Plazos clave, Garantías, Objeto y alcance, Requisitos, Criterios"

5. **Consolidando**
   - Icono: engranajes
   - Texto: "Consolidando resultados"

6. **Analizado**
   - Icono: check verde
   - Texto: "¡Análisis completado!"
   - Auto-redirect a pantalla de resultados en 2 segundos

**Timeout Warning (2 min antes del límite):**
```
⚠️ El análisis está demorando más de lo esperado
   pero continúa procesándose. Esto puede pasar con
   documentos extensos o escaneados
```

**Botón "Cancelar análisis":**
- Confirmación: "¿Querés cancelar el análisis en curso?"
- Cancela el procesamiento en backend
- El análisis queda en estado "Cancelado" en historial

---

### 4.7. DETALLE DEL ANÁLISIS - Vista Principal

**Esta es la pantalla MÁS IMPORTANTE del sistema. Aquí el usuario revisa y valida.**

**Layout: Dos columnas (Resultados + Visor PDF)**

```
┌─────────┬───────────────────────┬──────────────────┐
│         │  Pliego Mant IT       │                  │
│         │  [Estado: Analizado]  │  [Visor PDF →]   │
│ Sidebar │  ━━━━━━━━━━━━━━━━━━  │  (colapsable)    │
│         │                        │                  │
│         │  [Categorías ▾]        │                  │
│         │  ┌──────────────────┐ │                  │
│         │  │ ⚠️ Plazos clave  │ │                  │
│         │  │ 5/7 extraídos    │ │                  │
│         │  │ Sin revisar      │ │                  │
│         │  │ [Expandir ▼]     │ │                  │
│         │  └──────────────────┘ │                  │
│         │                        │                  │
│         │  ┌──────────────────┐ │                  │
│         │  │ ⚠️ Garantías      │ │                  │
│         │  │ 3/3 extraídos    │ │                  │
│         │  │ 1 en conflicto   │ │                  │
│         │  │ [Expandir ▼]     │ │                  │
│         │  └──────────────────┘ │                  │
│         │                        │                  │
│         │  [... más categorías] │                  │
│         │                        │                  │
│         │  [Validar análisis]   │                  │
└─────────┴───────────────────────┴──────────────────┘
```

**Header del Análisis:**
```
┌─────────────────────────────────────────────────┐
│ [← Volver al historial]                         │
│                                                  │
│ 📄 Pliego Mantenimiento IT — Ministerio Hacienda│
│    [Badge: Analizado]  25/7/2026  35 páginas    │
│    Creado por: agostorres04                     │
│                                                  │
│ [Re-analizar] [⋮ Más]                           │
└─────────────────────────────────────────────────┘
```

**Panel de Categorías (Columna Izquierda):**

Cada categoría se muestra como un card expandible/colapsable:

```
┌────────────────────────────────────────┐
│ ⚠️ Plazos clave ⭐ CRÍTICA             │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                        │
│ Estado: Sin revisar                    │
│ 5 de 7 plazos extraídos                │
│ 2 no encontrados                       │
│ Confianza promedio: Media              │
│                                        │
│ [Expandir detalles ▼]                 │
└────────────────────────────────────────┘
```

**Indicadores Visuales por Estado:**

1. **Categoría Crítica Pendiente:**
   - Icono: ⚠️ (triángulo advertencia)
   - Badge: "⭐ CRÍTICA" en naranja
   - Borde izquierdo: naranja (4px)
   - Estado: "Sin revisar"

2. **Categoría con Conflictos:**
   - Icono: ❌
   - Borde: rojo
   - Texto: "1 campo en conflicto"

3. **Categoría Revisada:**
   - Icono: ✓
   - Borde: verde
   - Estado: "Revisada"
   - Timestamp: "Revisada el 25/7 a las 14:30 por agostorres04"

4. **Categoría Fallida:**
   - Icono: 🔴
   - Borde: rojo punteado
   - Texto: "Error al analizar esta categoría"
   - Botón: [Reintentar]

**Orden de las Categorías (de arriba hacia abajo):**

1. **Con conflictos** (primero las críticas)
2. **Críticas sin revisar**
3. **No críticas sin revisar**
4. **Críticas revisadas**
5. **No críticas revisadas**

Esto asegura que la atención vaya primero a lo urgente.

---

### 4.8. DETALLE DE CATEGORÍA (Expandida)

**Cuando el usuario hace click en "Expandir detalles", el card se expande:**

```
┌────────────────────────────────────────────────────┐
│ ⚠️ Plazos clave ⭐ CRÍTICA              [Colapsar ▲]│
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                                    │
│ Se encontraron 5 plazos clave. El sistema extrajo │
│ fechas y plazos relativos del pliego.             │
│                                                    │
│ 📄 Fuente principal: pliego-principal.pdf pág. 8  │
│                                                    │
│ ▼ Campos extraídos (ordenados por severidad):     │
│                                                    │
│ ┌────────────────────────────────────────────────┐│
│ │ ❌ Presentación de ofertas [EN CONFLICTO]      ││
│ │                                                ││
│ │ Valor 1 (pliego-principal.pdf, pág 8):        ││
│ │ "15 de agosto de 2026, 10:00 hs"              ││
│ │ Confianza: Alta                                ││
│ │                                                ││
│ │ Valor 2 (circular-aclaratoria.pdf, pág 1):    ││
│ │ "20 de agosto de 2026, 10:00 hs"              ││
│ │ Confianza: Alta                                ││
│ │                                                ││
│ │ [Resolver conflicto]                           ││
│ └────────────────────────────────────────────────┘│
│                                                    │
│ ┌────────────────────────────────────────────────┐│
│ │ ⚠️ Consultas [NO ENCONTRADO]                   ││
│ │                                                ││
│ │ No se encontró información sobre el plazo      ││
│ │ para consultas en los documentos analizados    ││
│ │                                                ││
│ │ [Agregar manualmente]                          ││
│ └────────────────────────────────────────────────┘│
│                                                    │
│ ┌────────────────────────────────────────────────┐│
│ │ ⚠️ Apertura [CONFIANZA: BAJA]                  ││
│ │                                                ││
│ │ Valor extraído:                                ││
│ │ "22 de agosto de 2026, 11:00 hs"              ││
│ │                                                ││
│ │ 📄 Fuente: pliego-principal.pdf, pág. 12      ││
│ │ Cita: "La apertura de sobres se realizará..." ││
│ │                                                ││
│ │ [Ver fuente] [Corregir]                        ││
│ └────────────────────────────────────────────────┘│
│                                                    │
│ ┌────────────────────────────────────────────────┐│
│ │ ✓ Mantenimiento de oferta [CONFIANZA: ALTA]   ││
│ │                                                ││
│ │ "30 días corridos desde la fecha de apertura" ││
│ │                                                ││
│ │ 📄 Fuente: pliego-principal.pdf, pág. 9       ││
│ │                                                ││
│ │ [Ver fuente]                                   ││
│ └────────────────────────────────────────────────┘│
│                                                    │
│ [...más campos...]                                 │
│                                                    │
│ [Marcar categoría como revisada]                  │
└────────────────────────────────────────────────────┘
```

**Estructura de un Campo Extraído:**

Cada campo dentro de la categoría se muestra como un sub-card con:

1. **Encabezado:**
   - Icono según estado (❌ ⚠️ ✓)
   - Nombre del campo
   - Badge de estado/confianza

2. **Contenido:**
   - Valor extraído (o mensaje de estado)
   - Cita textual (colapsada a 2 líneas, expandible)
   - Fuente: archivo + página

3. **Acciones:**
   - Botones según el estado del campo

**Estados de Campo y sus Componentes:**

**1. EN CONFLICTO:**
```
┌────────────────────────────────────────┐
│ ❌ [Nombre campo] [EN CONFLICTO]       │
│                                        │
│ Valor 1 (doc-1.pdf, pág X):           │
│ "[texto del valor]"                   │
│ Confianza: [nivel]                    │
│                                        │
│ Valor 2 (doc-2.pdf, pág Y):           │
│ "[texto del valor]"                   │
│ Confianza: [nivel]                    │
│                                        │
│ [Resolver conflicto]                   │
└────────────────────────────────────────┘
```
- Borde: rojo
- Fondo: rojo muy claro
- Botón: rojo primario

**2. NO ENCONTRADO:**
```
┌────────────────────────────────────────┐
│ ⚠️ [Nombre campo] [NO ENCONTRADO]      │
│                                        │
│ No se encontró este dato en el pliego │
│                                        │
│ [Agregar manualmente]                  │
└────────────────────────────────────────┘
```
- Borde: amarillo
- Fondo: amarillo muy claro
- Botón: amarillo/naranja

**3. CONFIANZA BAJA:**
```
┌────────────────────────────────────────┐
│ ⚠️ [Nombre campo] [CONFIANZA: BAJA]    │
│                                        │
│ Valor extraído:                        │
│ "[texto del valor]"                   │
│                                        │
│ 📄 Fuente: archivo.pdf, pág. X        │
│ Cita: "[fragmento textual]"           │
│                                        │
│ [Ver fuente] [Corregir]                │
└────────────────────────────────────────┘
```
- Borde: naranja
- Fondo: naranja muy claro
- Botones destacados

**4. CONFIANZA MEDIA:**
```
┌────────────────────────────────────────┐
│ ℹ️ [Nombre campo] [CONFIANZA: MEDIA]   │
│                                        │
│ "[texto del valor]"                   │
│                                        │
│ 📄 Fuente: archivo.pdf, pág. X        │
│                                        │
│ [Ver fuente] [Corregir]                │
└────────────────────────────────────────┘
```
- Borde: azul claro
- Fondo: neutro
- Botones normales

**5. CONFIANZA ALTA:**
```
┌────────────────────────────────────────┐
│ ✓ [Nombre campo] [CONFIANZA: ALTA]     │
│                                        │
│ "[texto del valor]"                   │
│                                        │
│ 📄 Fuente: archivo.pdf, pág. X        │
│                                        │
│ [Ver fuente]                           │
└────────────────────────────────────────┘
```
- Borde: verde claro
- Fondo: neutro
- Botón secundario

**6. NO APLICA:**
```
┌────────────────────────────────────────┐
│ ℹ️ [Nombre campo] [NO APLICA]          │
│                                        │
│ El pliego declara explícitamente que  │
│ este requisito no se exige            │
│                                        │
│ 📄 Fuente: archivo.pdf, pág. X        │
│ Cita: "[fragmento textual que lo      │
│ respalda]"                            │
│                                        │
│ [Ver fuente]                           │
└────────────────────────────────────────┘
```
- Borde: azul claro
- Fondo: azul muy claro
- Badge: "NO APLICA" en azul
- Icono: ℹ️ (información)
- Siempre incluye cita textual obligatoria

**7. MODIFICADO POR USUARIO:**
```
┌────────────────────────────────────────┐
│ ✏️ [Nombre campo] [MODIFICADO]          │
│                                        │
│ Valor actual:                          │
│ "[texto corregido por usuario]"       │
│                                        │
│ Valor original del sistema:            │
│ "[texto extraído]" (tachado/gris)     │
│                                        │
│ Modificado por agostorres04 el 25/7   │
│                                        │
│ [Ver fuente] [Editar]                  │
└────────────────────────────────────────┘
```
- Borde: azul
- Badge: "MODIFICADO" en azul
- Muestra ambos valores (original + corregido)

---

### 4.9. MODAL: Resolver Conflicto

**Se abre al hacer click en "Resolver conflicto"**

```
┌──────────────────────────────────────────────┐
│  Resolver conflicto                    [X]   │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                              │
│  Campo: Presentación de ofertas              │
│                                              │
│  Seleccioná el valor correcto:               │
│                                              │
│  ○ 15 de agosto de 2026, 10:00 hs           │
│     📄 pliego-principal.pdf, pág. 8         │
│     Confianza: Alta                          │
│     Cita: "Las ofertas deberán..."          │
│     [Ver en documento]                       │
│                                              │
│  ○ 20 de agosto de 2026, 10:00 hs           │
│     📄 circular-aclaratoria.pdf, pág. 1     │
│     Confianza: Alta                          │
│     Cita: "Se prorroga la fecha límite..."  │
│     [Ver en documento]                       │
│                                              │
│  [Cancelar]              [Confirmar]        │
└──────────────────────────────────────────────┘
```

**Comportamiento:**
- Radio buttons para elegir uno de los valores
- Al hacer click en "Ver en documento", abre el visor PDF con esa cita resaltada
- "Confirmar" guarda la elección y cierra el modal
- El valor descartado se guarda en el registro como "Descartado por usuario"
- El campo pasa de "En conflicto" a "Extraído" con el valor elegido

---

### 4.10. MODAL: Agregar Manualmente / Corregir

**Se abre al hacer click en "Agregar manualmente" o "Corregir"**

```
┌──────────────────────────────────────────────┐
│  Corregir campo                        [X]   │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                              │
│  Campo: Apertura de ofertas                  │
│                                              │
│  Valor actual:                               │
│  [22 de agosto de 2026, 11:00 hs]           │
│                                              │
│  ───────────────────────────────────────     │
│                                              │
│  Valor original del sistema:                 │
│  "22 de agosto de 2026, 11:00 hs"           │
│  Confianza: Baja                             │
│                                              │
│  📄 Fuente: pliego-principal.pdf, pág. 12   │
│  Cita: "La apertura de sobres se realizará  │
│  el día veintidós de agosto del corriente   │
│  año, a las once horas, en la sede..."      │
│                                              │
│  [Ver en documento]                          │
│                                              │
│  ───────────────────────────────────────     │
│                                              │
│  Justificación (opcional):                   │
│  [_________________________________]         │
│                                              │
│  [Cancelar]              [Guardar]          │
└──────────────────────────────────────────────┘
```

**Comportamiento:**
- Input editable con el valor actual
- Muestra el valor original del sistema (no editable, para referencia)
- Muestra la cita completa del sistema
- Botón "Ver en documento" abre el visor con la cita resaltada
- Campo opcional para justificación
- "Guardar" registra: valor corregido, quién, cuándo, justificación
- El campo pasa a estado "MODIFICADO"

---

### 4.11. VISOR DE PDF (Columna Derecha)

**Panel lateral derecho, colapsable, con visor de PDF embebido.**

```
┌──────────────────────────────────────┐
│ [< Colapsar]    📄 pliego-principal  │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                      │
│  [Página anterior] 8/35 [Página →]  │
│  [Zoom -] 100% [Zoom +]             │
│                                      │
│ ┌──────────────────────────────────┐│
│ │                                  ││
│ │    [Contenido del PDF]           ││
│ │                                  ││
│ │    Texto resaltado en amarillo   ││
│ │    cuando se hace "Ver fuente"   ││
│ │                                  ││
│ │                                  ││
│ │                                  ││
│ └──────────────────────────────────┘│
│                                      │
│  [Descargar PDF]                    │
└──────────────────────────────────────┘
```

**Funcionalidades:**
- **Colapsar/Expandir:** El panel se puede ocultar para dar más espacio a los resultados
- **Navegación:** botones anterior/siguiente, input de página, total de páginas
- **Zoom:** botones +/- o slider
- **Resaltado:** cuando se hace click en "Ver fuente", el texto de la cita se resalta en amarillo
- **Múltiples citas:** si un campo tiene varias citas, aparecen flechas para navegar entre ellas
- **Cambio de documento:** si hay múltiples documentos, dropdown en el header para cambiar

**Estados:**
- **Sin documento abierto:** muestra placeholder "Hacé click en 'Ver fuente' para ver la cita en el documento"
- **Cargando:** spinner mientras se carga el PDF
- **Error:** mensaje si el PDF no se puede cargar

---

### 4.12. BOTÓN DE VALIDACIÓN (Footer Fijo)

**En el footer de la pantalla de detalle, siempre visible:**

```
┌──────────────────────────────────────────────┐
│                                              │
│  [Validar análisis]                         │
│                                              │
└──────────────────────────────────────────────┘
```

**Estados del Botón:**

**1. Deshabilitado (condiciones no cumplidas):**
- Gris, cursor not-allowed
- Tooltip o mensaje arriba explicando qué falta:
  ```
  ⚠️ Antes de validar:
     • Revisá las 3 categorías críticas
     • Resolvé 2 conflictos pendientes
  ```
  Con links directos a cada categoría/conflicto

**2. Habilitado (condiciones cumplidas):**
- Verde primario
- Texto: "Validar análisis"
- Click → Modal de confirmación

**Modal de Confirmación:**

```
┌──────────────────────────────────────────┐
│  Validar análisis                  [X]   │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                          │
│  ¿Estás seguro de que deseas validar    │
│  este análisis?                          │
│                                          │
│  Revisaste las 3 categorías críticas:   │
│  ✓ Plazos clave                          │
│  ✓ Garantías                             │
│  ✓ Causales de rechazo                   │
│                                          │
│  No quedan conflictos sin resolver       │
│                                          │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                          │
│  ☐ Confirmo que revisé el análisis       │
│     completo, incluyendo las fuentes     │
│     citadas, y que no me basé            │
│     únicamente en los resúmenes          │
│     generados por IA                     │
│                                          │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                          │
│  Al validar, este análisis quedará       │
│  marcado como listo para usar en la      │
│  evaluación de la licitación            │
│                                          │
│  [Cancelar]         [Validar]           │
└──────────────────────────────────────────┘
```

**Requisitos para habilitar el botón "Validar":**
1. Las 3 categorías críticas deben estar marcadas como "Revisada"
2. No pueden quedar conflictos sin resolver
3. **El checkbox de confirmación debe estar marcado**

Sin estas 3 condiciones cumplidas, el botón permanece deshabilitado.

**Post-validación:**
- El estado del análisis cambia a "Validado"
- Badge verde en el header
- Se registra: quién validó, cuándo
- Toast de confirmación: "✓ Análisis validado correctamente"

---

## 5. Componentes de Diseño

### 5.1. Botones

**Primario:**
- Fondo: azul (#2563EB)
- Texto: blanco
- Hover: azul más oscuro
- Disabled: gris claro, texto gris medio
- Uso: acción principal (Siguiente, Guardar, Validar)

**Secundario:**
- Fondo: blanco
- Borde: gris
- Texto: gris oscuro
- Hover: fondo gris muy claro
- Uso: acciones secundarias (Cancelar, Volver)

**Peligro:**
- Fondo: rojo (#DC2626)
- Texto: blanco
- Hover: rojo más oscuro
- Uso: acciones destructivas (Eliminar, Cancelar análisis)

**Ghost:**
- Sin fondo ni borde
- Texto: azul
- Hover: subrayado
- Uso: acciones terciarias (Ver fuente, Expandir)

**Tamaños:**
- Small: 32px alto, padding 8px 12px
- Medium: 40px alto, padding 10px 16px (default)
- Large: 48px alto, padding 12px 24px

### 5.2. Inputs

**Text Input:**
```
┌─────────────────────────────────┐
│ [Label]                         │
│ ┌─────────────────────────────┐ │
│ │ Placeholder...              │ │
│ └─────────────────────────────┘ │
│ [Mensaje de ayuda]              │
└─────────────────────────────────┘
```
- Altura: 40px
- Borde: gris claro
- Focus: borde azul
- Error: borde rojo + mensaje rojo debajo
- Disabled: fondo gris muy claro

**Textarea:**
- Igual que text input
- Mínimo 80px alto
- Resizable verticalmente

**Select/Dropdown:**
- Igual que text input
- Icono flecha abajo a la derecha
- Opciones en menú flotante

**Checkbox:**
- 20x20px
- Borde: gris
- Checked: fondo azul, checkmark blanco

**Radio button:**
- 20x20px circular
- Borde: gris
- Selected: centro azul relleno

### 5.3. Badges/Tags

**Estados de Análisis:**

- **En cola:** Gris `⏳ En cola`
- **Analizando:** Azul animado `⚙️ Analizando...`
- **Analizado:** Amarillo `⚠️ Analizado`
- **Validado:** Verde `✓ Validado`
- **Error:** Rojo `✗ Error`
- **Cancelado:** Gris `✗ Cancelado`

**Confianza:**
- **Alta:** Verde `✓ Alta`
- **Media:** Amarillo `⚠️ Media`
- **Baja:** Naranja/rojo `⚠️ Baja`

**Categoría Crítica:**
- Naranja `⭐ CRÍTICA`

**Formato:**
- Padding: 4px 8px
- Border radius: 4px
- Fuente: 12px, bold
- Mayúsculas

### 5.4. Cards

**Card Básico:**
```
┌────────────────────────────────┐
│ [Contenido]                    │
│                                │
└────────────────────────────────┘
```
- Fondo: blanco
- Borde: 1px gris claro
- Border radius: 8px
- Padding: 16px
- Sombra sutil: 0 1px 3px rgba(0,0,0,0.1)

**Card Hover (clickeable):**
- Hover: sombra más pronunciada, cursor pointer

**Card con Estado (conflicto, advertencia):**
- Borde izquierdo: 4px color del estado
- Fondo: color muy claro del estado

### 5.5. Modales

```
[Overlay oscuro 50% opacidad]

┌────────────────────────────────┐
│ [Título]                  [X]  │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│                                │
│ [Contenido]                    │
│                                │
│                                │
│ [Botones de acción]            │
└────────────────────────────────┘
```
- Ancho máximo: 600px
- Centrado vertical y horizontal
- Animación: fade in + scale
- Cerrar: click en X, click fuera, ESC

### 5.6. Tooltips

- Fondo: gris oscuro (#1F2937)
- Texto: blanco, 14px
- Padding: 8px 12px
- Border radius: 4px
- Flecha apuntando al elemento
- Aparece en hover después de 500ms

### 5.7. Toast/Notificaciones

```
┌────────────────────────────────┐
│ ✓ Análisis validado con éxito  │
└────────────────────────────────┘
```
- Posición: top-right
- Ancho: 300-400px
- Auto-dismiss: 4 segundos
- Colores según tipo:
  - Éxito: verde
  - Error: rojo
  - Advertencia: amarillo
  - Info: azul

---

## 6. Sistema Visual y Tokens

### 6.1. Paleta de Colores

**Colores Primarios:**
- **Primary (Azul):** #2563EB (botones, links, activo)
- **Primary Dark:** #1D4ED8 (hover)
- **Primary Light:** #DBEAFE (fondos suaves)

**Colores de Estado:**
- **Success (Verde):** #10B981 (validado, confianza alta)
- **Warning (Amarillo):** #F59E0B (analizado, advertencias)
- **Error (Rojo):** #DC2626 (conflictos, errores)
- **Info (Azul claro):** #3B82F6 (información)
- **Critical (Naranja):** #EA580C (categorías críticas)

**Neutrales:**
- **Gray 50:** #F9FAFB (fondos)
- **Gray 100:** #F3F4F6 (fondos suaves)
- **Gray 200:** #E5E7EB (bordes)
- **Gray 300:** #D1D5DB (bordes hover)
- **Gray 400:** #9CA3AF (texto secundario)
- **Gray 500:** #6B7280 (texto deshabilitado)
- **Gray 600:** #4B5563 (texto normal)
- **Gray 700:** #374151 (texto principal)
- **Gray 900:** #111827 (títulos, énfasis)

**Fondo de Página:**
- **Background:** #F9FAFB (Gray 50)

### 6.2. Tipografía

**Familia:**
- **Sans:** Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
- **Mono:** "Fira Code", "SF Mono", Consolas, monospace (para citas de código)

**Escalas:**

| Uso | Tamaño | Weight | Line Height |
|-----|--------|--------|-------------|
| H1 (Títulos principales) | 30px | 700 | 1.2 |
| H2 (Subtítulos) | 24px | 600 | 1.3 |
| H3 (Secciones) | 20px | 600 | 1.4 |
| H4 (Subsecciones) | 18px | 600 | 1.4 |
| Body Large | 16px | 400 | 1.5 |
| Body (Default) | 14px | 400 | 1.5 |
| Body Small | 12px | 400 | 1.4 |
| Caption | 11px | 400 | 1.3 |
| Button | 14px | 600 | 1 |
| Badge | 12px | 700 | 1 |

**Color de Texto:**
- Principal: Gray 900
- Secundario: Gray 600
- Deshabilitado: Gray 400
- Links: Primary Blue
- Error: Error Red

### 6.3. Espaciado

**Sistema de 4px base:**
- **xs:** 4px
- **sm:** 8px
- **md:** 16px (default)
- **lg:** 24px
- **xl:** 32px
- **2xl:** 48px
- **3xl:** 64px

**Aplicaciones:**
- Padding interno de componentes: md (16px)
- Gaps entre elementos: sm-md (8-16px)
- Márgenes entre secciones: lg-xl (24-32px)
- Separación de bloques: 2xl (48px)

### 6.4. Bordes y Sombras

**Border Radius:**
- **sm:** 4px (badges, inputs)
- **md:** 8px (cards, botones)
- **lg:** 12px (modales)
- **full:** 9999px (avatares)

**Sombras:**
- **sm:** 0 1px 2px rgba(0,0,0,0.05)
- **md:** 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06)
- **lg:** 0 10px 15px rgba(0,0,0,0.1), 0 4px 6px rgba(0,0,0,0.05)
- **xl:** 0 20px 25px rgba(0,0,0,0.1), 0 10px 10px rgba(0,0,0,0.04)

### 6.5. Iconografía

**Librería:** [Lucide React](https://lucide.dev) (npm: `lucide-react`)

**Tamaños:**
- **Small:** 16px (inline con badges, texto)
- **Medium:** 20px (default - botones, inputs)
- **Large:** 24px (headers, navegación)
- **XLarge:** 32px (ilustraciones, estados vacíos)

**Mapeo de Iconos del Sistema:**

| Contexto | Icono Lucide | Uso |
|----------|--------------|-----|
| **Documento** | `FileText` | Archivos, pliegos |
| **Calendario** | `Calendar` | Fechas, timestamps |
| **Clipboard** | `ClipboardCheck` | Progreso, categorías revisadas |
| **Búsqueda** | `Search` | Buscadores |
| **Menú principal** | `List` | Navegación principal |
| **Más opciones** | `MoreVertical` | Menús contextuales (⋮) |
| **Expandir/Colapsar** | `ChevronDown` / `ChevronUp` | Dropdowns, colapsables |
| **Volver** | `ArrowLeft` | Navegación atrás |
| **Recargar** | `RefreshCw` | Re-analizar |
| **Subir** | `Upload` | Upload de archivos |
| **Cerrar** | `X` | Cerrar modales, eliminar tags |

**Iconos de Estado:**

| Estado | Icono Lucide | Color | Uso |
|--------|--------------|-------|-----|
| **Éxito** | `CheckCircle` | Success `#10B981` | Validado, confianza alta |
| **Error** | `XCircle` | Error `#DC2626` | Conflictos, errores |
| **Advertencia** | `AlertTriangle` | Warning/Critical | No encontrado, baja confianza |
| **Info** | `Info` | Info `#3B82F6` | Información, no aplica |
| **Crítico** | `AlertCircle` | Critical `#EA580C` | Categorías críticas pendientes |
| **En proceso** | `Loader2` | Primary Blue | Analizando (animado con `animate-spin`) |
| **Pendiente** | `Clock` | Gray | En cola |

**Iconos de Confianza (Campos):**

| Nivel | Icono Lucide | Color |
|-------|--------------|-------|
| Alta | `CheckCircle` | Success |
| Media | `Info` | Info Blue |
| Baja | `AlertTriangle` | Critical Orange |
| En Conflicto | `XCircle` | Error Red |
| No Encontrado | `AlertTriangle` | Warning |
| No Aplica | `Info` | Info Blue |

**Iconos de Navegación:**

| Elemento | Icono Lucide |
|----------|--------------|
| Dashboard | `LayoutDashboard` |
| Historial | `History` |
| Ayuda | `HelpCircle` |
| Usuario | `User` |
| Salir | `LogOut` |
| Configuración | `Settings` |

**Guidelines:**
- Siempre acompaña iconos de acciones con texto (excepto iconos universales: ⋮, ✓, ✗)
- Color: hereda del contexto o aplica color de estado
- Usa `Loader2` con `animate-spin` para estados de carga
- Mantén consistencia: mismo icono para mismo concepto en toda la app

**Ejemplo de Uso:**
```tsx
import { FileText, AlertTriangle, CheckCircle } from 'lucide-react'

<button className="flex items-center gap-2">
  <FileText size={20} />
  Ver pliego
</button>

<span className="flex items-center gap-1 text-error">
  <AlertTriangle size={16} />
  No encontrado
</span>
```

---

## 7. Estados y Feedback

### 7.1. Estados de Interacción

**Hover:**
- Botones: cambio de color de fondo
- Links: subrayado
- Cards: elevación de sombra
- Inputs: cambio sutil de borde

**Focus:**
- Outline azul (2px) para accesibilidad
- Focus visible en tab navigation

**Active/Pressed:**
- Botones: color más oscuro, sombra reducida
- Sensación táctil

**Disabled:**
- Opacidad 50%
- Cursor not-allowed
- Sin interacción hover

**Loading:**
- Spinner animado
- Skeleton loaders para contenido
- Texto "Cargando..." con puntos animados

### 7.2. Feedback Visual

**Éxito:**
- Toast verde con ✓
- Animación sutil de checkmark
- Sonido opcional (post-MVP)

**Error:**
- Toast rojo con ✗
- Shake animation en formularios
- Mensaje claro del problema

**Advertencia:**
- Toast/banner amarillo con ⚠️
- No bloquea, pero informa

**Info:**
- Toast azul con ℹ️
- Para notificaciones no urgentes

### 7.3. Animaciones

**Transiciones:**
- Duración estándar: 200ms
- Easing: ease-in-out
- Propiedades: opacity, transform, background-color

**Loaders:**
- Spinner: rotate 360deg, 1s linear infinite
- Skeleton: shimmer effect de izquierda a derecha
- Progress bar: animación de llenado

**Microinteracciones:**
- Botones: ligero scale en hover
- Cards: elevación suave
- Modales: fade + scale desde 95% a 100%
- Toasts: slide-in desde arriba/derecha

---

## 8. Responsive y Breakpoints

### 8.1. Breakpoints

**Desktop First (priorizamos escritorio según PRD):**

- **XL:** ≥1440px (monitores grandes)
- **LG:** ≥1024px (laptops, tablets horizontales) ← **Target principal**
- **MD:** ≥768px (tablets verticales)
- **SM:** ≥640px (móviles grandes)
- **XS:** <640px (móviles) ← **Soporte mínimo**

### 8.2. Layout Responsivo

**Desktop (≥1024px):**
- Sidebar: 240px fijo
- Contenido: dos columnas (60% resultados + 40% visor PDF)
- Visor PDF colapsable

**Tablet (768-1023px):**
- Sidebar: colapsable a 64px (solo iconos)
- Contenido: una columna, visor PDF en modal/overlay
- Navegación adaptada

**Móvil (<768px):**
- Sidebar: menú hamburguesa overlay
- Contenido: una columna, stack vertical
- Visor PDF: pantalla completa al hacer click
- Botones adaptados a táctil (mínimo 44px)

**Notas:**
- Móvil NO es prioridad en MVP (según PRD)
- Asegurar que sea usable, pero no optimizar
- Focus en experiencia de escritorio/laptop

---

## Fin del Documento

Este documento establece las especificaciones UX/UI base del sistema. A continuación se crearán:

1. **Wireframes detallados** de cada pantalla
2. **Flujos de usuario** paso a paso con screenshots
3. **Componentes reutilizables** en detalle
4. **Guía de implementación** para desarrollo

---

**Próximos pasos:**
- Validar con stakeholders
- Crear prototipos de alta fidelidad
- Testear con usuarios reales
- Iterar según feedback
