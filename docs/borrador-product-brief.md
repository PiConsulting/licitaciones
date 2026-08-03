# Borrador para pegar en `bmad-product-brief`

> Pegá todo este bloque como primer mensaje al arrancar `bmad-product-brief`. El agente va a seguir preguntando lo que falte — contestá ahí lo que no esté cubierto acá.

---

**Problema que resuelve el proyecto:**
Nuestro equipo participa en licitaciones y necesita revisar pliegos extensos y heterogéneos para decidir si conviene participar. Hacerlo manualmente es lento y propenso a errores u omisiones importantes (plazos, garantías, causales de rechazo).

**Qué hace el sistema:**
Analiza pliegos de licitación en PDF y extrae automáticamente 7 categorías clave:
1. Objeto y alcance
2. Requisitos de admisibilidad
3. Garantías
4. Plazos clave
5. Criterios de evaluación
6. Causales de rechazo
7. Anexos obligatorios

La salida queda en JSON estructurado (para consultas exactas, ej. filtrar por plazo o por organismo) y también vectorizada (para búsqueda semántica sobre el contenido).

**Alcance del MVP — qué incluye:**
- Subida manual de un pliego en PDF (mezcla de pliegos con texto nativo y pliegos escaneados)
- Extracción de las 7 categorías de arriba
- Frontend con 3 pantallas: Dashboard (resumen), Análisis de Pliegos (subida y disparo del análisis), Historial (listado, búsqueda, acciones)
- Pipeline: ingesta → chunking → 7 nodos de extracción en paralelo (uno por categoría) → nodo de merge y validación → storage

**Alcance del MVP — qué NO incluye (por ahora):**
- Scoring o puntaje por pliego (todavía no está definido qué mediría a nivel de negocio)
- "Radar de oportunidades" (sección a cargo de otro integrante del equipo; queda reservada en el sidebar pero no se construye en este MVP)
- El frontend **todavía no está construido** — hay capturas de referencia, pero son solo inspiración de estilo y flujo, no pantallas ya hechas para conectar

**Usuarios:**
El propio equipo del proyecto, uso interno por ahora (no es un producto público todavía).

**Decisiones técnicas ya tomadas** (para que el brief no las replantee de cero):
- Arquitectura hexagonal (puertos y adaptadores), capas domain / application / infrastructure / orchestration / api
- Stack inicial: Python, ChromaDB (vectores), LangGraph (orquestación), MarkItDown (ingesta de PDFs con texto nativo)
- Router de ingesta: MarkItDown para pliegos nativos, Azure Document Intelligence para escaneados
- Migración futura planeada (no en este MVP): Azure AI Search + Document Intelligence + Microsoft Agent Framework (MAF), a evaluar cuando haya datos reales de volumen y costo
- La extracción está dividida en 7 nodos independientes (uno por categoría), corriendo en paralelo — no es un solo nodo monolítico
- Cada nodo de extracción tiene su propio prompt y su propia recuperación semántica (glosario de sinónimos), porque los pliegos no usan siempre el mismo vocabulario para el mismo concepto
- Nodo de merge y validación que combina los 7 resultados en un único JSON y lo valida contra un schema Pydantic completo
- Cada campo extraído devuelve evidencia (cita del chunk de origen) y un nivel de confianza; confianza baja o campo no encontrado se marca para revisión humana, nunca se inventa un valor
- Se va a armar un golden set de 15-20 pliegos anotados a mano para medir la calidad de la extracción

**Metodología de desarrollo:**
- Planificación con BMAD Method (brief → PRD → UX → arquitectura → épicas/historias → chequeo de coherencia)
- Implementación historia por historia: BMAD solo alcanza para historias simples; BMAD + Spec Kit (SDD) para las historias más delicadas (los 7 nodos de extracción)
- Herramienta de trabajo: GitHub Copilot Chat en VS Code
- Ramas: `main` (protegida) / `develop` (integración) / `feature/<historia>` y `fix/<algo>` por historia

**Estimación de tiempo:**
~13-19 días hábiles (2.5-4 semanas) para el MVP completo, incluyendo diseño y construcción del frontend, más los 7 nodos de extracción y el nodo de merge.

**Equipo:**
Equipo chico, mixto — recién arrancando con estas herramientas puntuales (BMAD, Spec Kit, LangGraph en un proyecto real). Un integrante adicional se va a encargar más adelante de "Radar de oportunidades".
