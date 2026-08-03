---
title: Input para PRD v2 — Sistema de Análisis de Pliegos
proposito: Definiciones de producto que faltan o están ambiguas en el PRD v1.1
destinatario: bmad-prd
version: 2.0
created: 2026-07-30
---

# Input para PRD v2 — Definiciones de producto

Este documento contiene **únicamente definiciones de comportamiento del sistema**. No contiene decisiones de arquitectura, stack ni implementación: esas van en `input-arquitectura.md`, destinado a la fase de arquitectura.

Cada punto cierra una ambigüedad detectada en el PRD v1.1. Todos son normativos, y todos llevan su justificación explícita: una decisión sin fundamento escrito se vuelve a discutir en la primera reunión y se pierde el trabajo hecho.

---

---

## 2. Qué extrae el sistema

### 2.1. Se agrega una octava extracción: datos del procedimiento

**Decisión.** Se formaliza como categoría propia de extracción:

- Organismo convocante
- Número de expediente
- Número de procedimiento (licitación / contratación)
- Tipo de procedimiento: licitación pública, concurso de precios, contratación directa, subasta inversa, otro
- Presupuesto oficial y moneda
- Jurisdicción: nacional, provincial, municipal

**Por qué.** El PRD v1.1 pide en el historial (FR-5.2) que el sistema detecte automáticamente el organismo, pero no existe ninguna extracción que lo produzca: aparece como una columna de una tabla, como si fuera un dato que llega solo. Detectar el organismo es un problema de extracción tan real como detectar las garantías, y esconderlo dentro de una tabla del historial garantiza que nadie lo estime. Además, el número de expediente y el presupuesto oficial son datos que el ejecutivo necesita para decidir, y hoy no están en ninguna de las 7 categorías.

### 2.2. Diccionario de datos de las 8 categorías

**Por qué existe esta sección.** Es el hueco más grande del PRD v1.1: todo el producto se define como "extraemos 7 cosas" y las 7 cosas nunca se definen más allá del nombre. Sin este diccionario no se pueden escribir criterios de aceptación, no se puede anotar el conjunto de referencia, no se puede medir la calidad y no se pueden estimar las historias. Cada persona que lea "extraemos garantías" va a imaginar algo distinto.

**1. Objeto y alcance**
- Resumen del objeto (texto breve)
- Modalidad: bienes, servicios, obra, mixto
- Listado de ítems: descripción, cantidad, unidad, renglón
- Si admite oferta parcial (sí/no)
- Si admite ofertas alternativas (sí/no)
- Lugar de entrega o prestación
- Plazo de ejecución (texto)

**2. Requisitos de admisibilidad** — listado, cada uno con:
- Descripción
- Tipo: legal, técnico, económico-financiero, administrativo, experiencia
- Si es obligatorio
- Documento respaldatorio exigido
- Momento de presentación: con la oferta, previo a la apertura, pre-adjudicación, no especificado
- Si es subsanable

**3. Garantías** — listado, cada una con:
- Tipo: mantenimiento de oferta, cumplimiento de contrato, anticipo, impugnación, otra
- Base de cálculo: porcentaje o monto fijo
- Porcentaje y/o monto, con moneda
- Sobre qué se calcula el porcentaje (presupuesto oficial, monto ofertado, etc.)
- Formas admitidas: póliza de caución, aval bancario, depósito, cheque certificado, pagaré, otra
- Plazo de constitución (texto)
- Plazo de vigencia (texto)

**4. Plazos clave** — listado, cada uno con:
- Tipo: consultas, respuesta a consultas, visita a obra, presentación de ofertas, apertura, mantenimiento de oferta, adjudicación, firma de contrato, inicio de ejecución, entrega, garantía técnica, impugnación, otro
- Fecha (sólo si el pliego la enuncia explícitamente) y hora
- Expresión relativa, si corresponde ("10 días hábiles desde la notificación")
- Texto original tal como aparece en el pliego — **siempre presente**
- Si es prorrogable
- Lugar (dónde se presenta / dónde se abre)

**5. Criterios de evaluación**
- Método: menor precio, puntaje ponderado, mejor relación precio-calidad, por renglón, otro
- Listado de criterios: nombre, ponderación en %, descripción, tipo (precio, técnico, experiencia, plazo, otro)
- Fórmula de evaluación (texto)
- Puntaje técnico mínimo para pasar, si existe

**6. Causales de rechazo** — listado, cada una con:
- Descripción
- Si es de rechazo automático o sujeta a evaluación
- Si es subsanable
- Momento en que aplica: admisión, evaluación, adjudicación, no especificado

**7. Anexos obligatorios** — listado, cada uno con:
- Identificador ("Anexo III", "Formulario B")
- Nombre y descripción
- Si debe completarse
- Si debe firmarse
- Si está presente entre los documentos que el usuario subió

**8. Datos del procedimiento** — ver 2.1

**Por qué "subsanable" aparece en dos categorías.** En el régimen de contrataciones argentino, la diferencia entre un defecto subsanable y uno que provoca rechazo directo es exactamente lo que determina si conviene presentarse con documentación incompleta. Es el dato de mayor valor práctico dentro de causales de rechazo, y omitirlo convertiría al sistema en un listado de advertencias sin jerarquía.

### 2.3. Categorías críticas

**Decisión.** Tres categorías se consideran críticas: **plazos clave, garantías y causales de rechazo**. Reciben tratamiento diferenciado en revisión obligatoria (§4.4 y §6.3).

**Por qué esas tres.** Son las de mayor costo asimétrico de error. Perder una fecha de presentación deja afuera de la licitación sin recurso posible. Subdimensionar una garantía significa que la oferta se rechaza en el acto de apertura. No detectar una causal de rechazo hace que todo el trabajo posterior sea inútil. Los otros cinco errores producen una decisión peor informada, que es malo pero recuperable. La asimetría justifica tratarlas distinto.

---

## 3. Estados de un campo

### 3.1. Cuatro estados posibles

**Decisión.**

| Estado | Significado |
|---|---|
| **Extraído** | El sistema encontró el dato y lo respalda con una cita del documento |
| **No encontrado** | El sistema no pudo determinar el dato |
| **No aplica** | El pliego declara explícitamente que ese requisito no se exige |
| **En conflicto** | Dos documentos dan valores contradictorios para el mismo dato |

**Por qué.** El PRD v1.1 sólo contempla "encontrado" y "no encontrado", y eso colapsa dos situaciones opuestas en el mismo resultado en pantalla. "El pliego no exige garantía de mantenimiento de oferta" es una buena noticia que reduce el costo de participar. "No encontré la garantía de mantenimiento de oferta" es una alerta que obliga a leer el documento. Con un solo estado para ambas, el ejecutivo tiene que ir a verificar siempre, y el sistema pierde buena parte de su valor: el ahorro de tiempo viene justamente de no tener que verificar lo que ya está resuelto.

### 3.2. Regla del estado "No aplica"

**Decisión.** Sólo se asigna cuando existe una frase en el documento que declara la no exigencia, y el sistema debe citarla. Sin cita, el estado es "No encontrado".

**Por qué.** El default siempre tiene que ser el conservador. Marcar "no aplica" por ausencia de evidencia es el error más peligroso que puede cometer el sistema: le dice al usuario "no te preocupes por esto" cuando en realidad significa "no lo busqué bien". Exigir cita convierte una inferencia en una afirmación verificable.

### 3.3. Regla de las fechas relativas

**Decisión.** Cuando un plazo se expresa de forma relativa ("dentro de los 10 días hábiles de notificada la adjudicación"), **el sistema no calcula la fecha resultante**. Muestra la expresión tal como está en el pliego.

**Por qué.** Calcular esa fecha requiere conocer los feriados nacionales, provinciales y municipales aplicables, más la fecha exacta del evento disparador, que a menudo todavía no ocurrió. Un error en ese cálculo es silencioso: el sistema muestra una fecha con toda la apariencia de ser correcta y el ejecutivo la anota en su calendario. El costo de mostrar el texto crudo es que el usuario tiene que hacer la cuenta; el costo de calcular mal es perder la licitación.

---

## 4. Confianza y verificación

### 4.1. Todo valor debe tener respaldo verificable

**Decisión.** Todo campo con estado "Extraído" incluye al menos una cita textual del documento fuente, con su archivo y su página. Si el sistema no puede respaldar un valor con una cita presente en el documento, el campo pasa a "No encontrado".

**Por qué.** Reemplaza el requisito "cero falsos positivos" del PRD v1.1 (NFR-1.2), que era imposible de verificar: nadie puede demostrar que un modelo de lenguaje nunca va a inventar nada. En cambio, "todo valor tiene una cita que existe en el documento" sí se puede comprobar de forma automática y exhaustiva sobre cada campo de cada análisis. Es la diferencia entre una promesa y una garantía.

### 4.2. La confianza se muestra como nivel, y cada nivel indica una acción

**Decisión.** El usuario ve **Alta / Media / Baja**, no un porcentaje. Cada nivel tiene una semántica de acción definida:

| Nivel | Qué significa para el usuario |
|---|---|
| **Alta** | Puede tomarlo como válido sin abrir el documento fuente |
| **Media** | Debería verificar la cita antes de usarlo para decidir |
| **Baja** | No debe usarlo sin leer el documento original |

**Por qué el nivel y no el porcentaje.** Un "87%" comunica una precisión de medición que el sistema no tiene: es un valor heurístico, no una probabilidad calibrada. Mostrarlo como número invita a comparaciones que no significan nada — que un campo tenga 87% y otro 84% no dice que el primero sea más confiable. Tres niveles comunican lo mismo sin la falsa exactitud.

**Por qué definir la acción y no sólo la etiqueta.** Sin esta tabla, "confianza media" es una decoración de color que cada usuario interpreta a su manera y que ningún criterio de aceptación puede verificar. Definida por acción, la etiqueta se vuelve una instrucción, es testeable con usuarios reales, y no depende de cómo se calcule el score por dentro: si mañana cambia el método de cálculo, la semántica sigue siendo válida.

### 4.3. Se elimina el objetivo "menos del 10% de campos en revisión manual"

**Decisión.** Se elimina como umbral de aprobación. Se reemplaza por medir y reportar la tasa de revisión manual, sin umbral en el MVP.

**Por qué.** Dos razones. La primera es aritmética: con 8 categorías, ese objetivo equivale a menos de un campo por pliego, lo cual es irreal para un sistema recién construido. La segunda es más grave: el objetivo crea un incentivo contrario al producto. La forma más barata de cumplirlo es que el sistema se declare más seguro de lo que está, y eso degrada exactamente la garantía que el producto promete. **Nunca conviene poner un umbral de aprobación sobre una métrica que el propio sistema puede inflar.**

### 4.4. Casos que siempre exigen revisión, sin importar la confianza

**Decisión.**
- Un valor cuya cita no pudo verificarse en el documento
- Estado "No encontrado" o "En conflicto" en una categoría crítica
- Confianza Baja
- Un valor extraído de un anexo que contradice al documento principal

**Por qué el "no encontrado" en categoría crítica fuerza revisión.** Es contraintuitivo pero es el caso más peligroso de todos: un campo vacío no llama la atención. Si el sistema no encontró las causales de rechazo, el usuario ve una sección vacía y su interpretación natural es "este pliego no tiene causales especiales", cuando lo que pasó fue que el sistema falló. **La ausencia de información se lee como información.** Marcarla explícitamente es la única forma de romper esa lectura.

---

## 5. Múltiples documentos

### 5.1. El usuario designa el documento principal

**Decisión.** Al subir, el usuario indica cuál es el pliego principal. Los demás quedan como anexos o documentos complementarios. Si sube un solo archivo, se designa automáticamente.

**Por qué.** Inferirlo automáticamente es un problema de clasificación adicional, con su propia tasa de error, para resolver algo que el usuario ya sabe con certeza: él descargó los archivos y sabe cuál es el pliego. Un control en la pantalla de subida cuesta minutos de desarrollo y elimina una fuente de error entera.

### 5.2. Ante contradicciones, el sistema no elige

**Decisión.** Si dos documentos dan valores distintos para el mismo dato, el campo queda **En conflicto** y se muestran ambos valores con su documento de origen y su cita. El sistema no resuelve la contradicción.

**Por qué.** Es exactamente el caso donde el ejecutivo más necesita ayuda, y por eso mismo es el peor lugar para arriesgar una decisión automática. Si el sistema elige mal y muestra un solo valor, el error queda invisible: el usuario no tiene forma de saber que hubo una contradicción. Mostrar ambos convierte un error potencial en una decisión informada, y agrega valor real — porque detectar la contradicción es trabajo que el ejecutivo hoy hace a mano leyendo dos documentos en paralelo.

### 5.3. Unión vs. conflicto en categorías de tipo listado

**Decisión.** Cinco de las ocho categorías son listados (requisitos, garantías, plazos, causales, anexos). Para ellas:

- **Unión** cuando los ítems son distintos entre sí: se acumulan en un solo listado, cada uno mostrando su documento de origen.
- **Conflicto** cuando dos ítems son *el mismo ítem* y difieren en algún atributo. Sólo ese ítem queda En conflicto; el resto del listado se muestra normal.

**Qué hace que dos ítems sean "el mismo":**

| Categoría | Criterio de identidad |
|---|---|
| Garantías | Tipo de garantía |
| Plazos clave | Tipo de plazo |
| Anexos obligatorios | Identificador del anexo |
| Requisitos de admisibilidad | Descripción equivalente |
| Causales de rechazo | Descripción equivalente |

**Por qué hace falta esta regla.** Sin ella, la regla de conflicto de §5.2 es ambigua para la mayoría de las categorías. Si el pliego principal lista 4 requisitos y el anexo lista 6, una lectura la trata como contradicción y otra como suma. La respuesta correcta es que **un anexo que agrega requisitos es el comportamiento normal, no una contradicción** — para eso existen los anexos. La contradicción real es cuando ambos hablan del mismo ítem y dicen cosas distintas: dos garantías de cumplimiento con porcentajes distintos son un conflicto genuino, mientras que una garantía de cumplimiento y una de impugnación simplemente conviven.

**Por qué el criterio de identidad varía por categoría.** Porque la unicidad natural es distinta en cada una. No puede haber dos garantías de cumplimiento de contrato con porcentajes distintos, pero sí puede haber diez requisitos de admisibilidad diferentes. Un criterio único produciría falsos conflictos en unas categorías y falsas uniones en otras.

**Por qué el conflicto es por ítem y no por categoría entera.** Si un solo plazo está en conflicto, marcar toda la categoría "Plazos clave" como problemática obliga al usuario a revisar los otros ocho plazos que estaban perfectos. El objetivo del sistema es dirigir la atención, no dispersarla.

### 5.4. Circulares y aclaratorias quedan fuera del MVP

**Decisión.** Se pueden subir como documento complementario y se analizan como cualquier otro, pero **sin lógica de sobrescritura temporal**: una contradicción entre pliego y circular se marca En conflicto y la resuelve el usuario. Esta limitación debe ser visible en la interfaz, no sólo estar documentada.

**Por qué se dejan fuera.** Soportarlas correctamente exige que el análisis tenga noción de qué versión del pliego está vigente en cada momento, con fechas de emisión y precedencia temporal. Eso es un modelo de datos y una interfaz enteros, no un detalle.

**Por qué igual se pueden subir.** Porque el comportamiento degradado — marcarlas como conflicto — es útil de todos modos: el usuario ve que hay una discrepancia y sabe que la circular es posterior. Es peor rechazarlas que aceptarlas con una limitación conocida.

**Por qué la limitación tiene que estar en la interfaz.** Una limitación documentada en el PRD la lee el equipo; una limitación visible en pantalla la lee quien está por tomar una decisión con esos datos.

---

## 6. Comportamiento de la aplicación

### 6.1. Corrección de campos

**Decisión.**
- **Dentro del MVP:** el usuario puede modificar el valor de cualquier campo y marcarlo como validado. Se conserva el valor original junto con el corregido, quién lo corrigió y cuándo.
- **Fuera del MVP:** la edición estructural — agregar o quitar ítems de un listado, crear campos que el sistema no propuso.

**Por qué hay que aclararlo.** El PRD v1.1 se contradice consigo mismo: lista "edición manual de campos" como fuera del MVP (§3.2) y simultáneamente la pide en FR-4.4 y FR-7.3, sin definir en ningún lado la diferencia entre "corregir" y "editar". Un desarrollador va a implementar una de las dos y va a estar mal.

**Por qué se conserva el valor original.** Porque la diferencia entre lo que el sistema extrajo y lo que el humano corrigió es la única medición gratuita y continua de calidad que vas a tener una vez en producción. Descartar el original es tirar esa información.

### 6.2. Re-analizar genera una nueva versión

**Decisión.** No sobrescribe el análisis anterior. El historial muestra la última versión y permite consultar las anteriores.

**Por qué.** El modo de trabajo previsto para todo el proyecto es iterar sobre los prompts de cada categoría. Sin versionado no se puede comparar el resultado antes y después de un ajuste, que es literalmente la actividad principal del equipo. Sobrescribir también destruye las correcciones del usuario, que son datos que costaron trabajo humano.

### 6.3. Validación de un análisis

**Decisión.** Un análisis sólo puede marcarse como **Validado** cuando se cumplen dos condiciones: el usuario revisó explícitamente las tres categorías críticas, y no quedan campos En conflicto sin resolver.

**Por qué.** El PRD v1.1 dice que "la decisión final sigue siendo humana", pero eso es una frase declarativa sin ningún mecanismo que la respalde: nada impide que el ejecutivo mire la pantalla tres segundos y decida participar. Como el sistema está diseñado para generar confianza, esa confianza se puede volver exceso de confianza, y **el modo de falla más probable del producto no es que extraiga mal, sino que extraiga bien casi siempre y el usuario deje de verificar.** La validación obligatoria es la contramedida, y además deja registro de quién revisó qué — que es lo único concreto que se puede ofrecer frente a la pregunta de responsabilidad que hoy nadie respondió.

### 6.4. Progreso por etapas, no por porcentaje

**Decisión.** El usuario ve la etapa en curso: *En cola* → *Extrayendo texto (n de m documentos)* → *Indexando* → *Analizando categorías (n de 8)* → *Consolidando* → *Analizado*.

**Por qué.** Un porcentaje continuo sobre etapas de duración heterogénea y desconocida es una barra falsa: se calcula inventando pesos por etapa y termina quedándose en 90% durante minutos, que es la peor experiencia posible. Las etapas nombradas son honestas, informan qué está pasando, y tienen la ventaja secundaria de que cuando algo se cuelga se sabe dónde.

### 6.5. Resultados parciales

**Decisión.** Si una categoría no puede extraerse, el análisis continúa y se muestra el resultado con esa categoría marcada como fallida, con opción de reintentar sólo esa categoría. El análisis completo sólo falla si no se puede leer el documento.

**Por qué.** Un pliego con 7 de 8 categorías extraídas es útil; descartarlo entero desperdicia todo el procesamiento hecho y obliga a repetirlo. Como las categorías se extraen de forma independiente, no hay razón para que el fallo de una arrastre a las demás.

### 6.6. Eliminación

**Decisión.** Elimina el pliego, sus documentos y sus análisis. Se conserva el registro de que hubo una eliminación, quién y cuándo, no el contenido.

**Por qué.** El PRD v1.1 menciona que el usuario puede eliminar pliegos pero no define qué significa. Sin definición, se implementa como ocultar la fila del historial y los documentos quedan almacenados para siempre — que es lo contrario de lo que el usuario cree que está haciendo cuando presiona "Eliminar".

### 6.7. Visibilidad entre usuarios

**Decisión.** Todos los usuarios autenticados ven todos los análisis. Cada análisis registra quién lo creó.

**Por qué.** El equipo comercial trabaja sobre las mismas licitaciones; aislar por usuario significaría que dos ejecutivos analicen el mismo pliego sin enterarse. Con 1 o 2 usuarios en el MVP, el aislamiento agrega complejidad sin ningún beneficio. La separación por empresa ya está prevista como post-2.0 y guardar quién creó cada análisis desde ahora la deja preparada.

---

## 7. Flujos

El PRD v1.1 narra un solo flujo (§2.3, el escenario típico) y no cubre ninguno de los casos que introdujeron las decisiones anteriores. Estos seis lo reemplazan.

### Flujo 1 — Análisis nuevo

1. El usuario entra a **Analizar pliego** y selecciona uno o varios archivos.
2. El navegador valida **formato, tamaño individual, tamaño total y cantidad** antes de subir nada. Si algo falla, muestra el mensaje correspondiente (§8.3) y no sube el archivo.
3. El usuario **designa el documento principal**. Si subió uno solo, queda designado automáticamente.
4. El usuario dispara el análisis.
5. El sistema verifica si alguno de los archivos ya fue analizado antes. Si lo fue → **Flujo 4**.
6. El sistema cuenta las páginas de cada documento. Si excede el máximo, rechaza con el mensaje correspondiente **antes de procesar nada**. Si supera las 100 páginas, muestra una advertencia de demora pero continúa.
7. El análisis entra en cola con estado **En cola**.
8. El usuario ve el avance por etapas (§6.4). Puede navegar a otra pantalla y volver.
9. Al terminar, el estado pasa a **Analizado** y se muestra el resultado: las 8 categorías, cada campo con su valor, su estado y su nivel de confianza.
10. El usuario revisa. Para cualquier campo puede abrir el documento fuente, que se posiciona en la página correcta con el texto resaltado.
11. El usuario corrige los valores que hagan falta.
12. El usuario intenta validar el análisis → **Flujo 3**.

### Flujo 2 — Campos que requieren atención

Ocurre dentro del Flujo 1, en el paso 10. El sistema dirige la atención en este orden:

1. **Campos En conflicto** — se muestran primero, con ambos valores y sus documentos de origen. El usuario elige uno; el descartado se conserva en el registro. Es obligatorio resolverlos para validar.
2. **Campos No encontrado en categoría crítica** — marcados como pendientes de verificación. El usuario confirma que el dato no está en el pliego, o lo carga manualmente.
3. **Campos con confianza Baja** — marcados para lectura del documento original.
4. **Campos con confianza Media** — marcados para verificación de la cita.

**Por qué en ese orden.** De mayor a menor costo de equivocarse. Un conflicto sin resolver significa que hay un dato contradictorio en la mesa; un campo de confianza media significa que probablemente esté bien. Ordenar por severidad hace que, si el usuario sólo revisa las primeras tres cosas, esas hayan sido las importantes.

### Flujo 3 — Validación

1. El usuario presiona **Validar análisis**.
2. El sistema verifica dos condiciones: que las tres categorías críticas hayan sido revisadas explícitamente, y que no queden campos En conflicto.
3. Si falta algo, **bloquea** y muestra exactamente qué: qué categorías faltan revisar y cuántos conflictos quedan, con acceso directo a cada uno.
4. Si todo está en orden, el análisis pasa a **Validado** y queda registrado quién lo validó y cuándo.

**Qué cuenta como "revisar una categoría".** Abrir su detalle y marcarla explícitamente como revisada. No alcanza con que la pantalla se haya mostrado.

**Por qué no alcanza con mostrarla.** Porque entonces el requisito se cumple con hacer scroll, y el control no controla nada.

### Flujo 4 — Documento duplicado

1. Al disparar el análisis, el sistema detecta que un archivo idéntico ya fue analizado.
2. Informa cuándo se analizó y quién lo hizo.
3. Ofrece tres caminos: **ver el análisis existente**, **analizarlo de nuevo** (genera una versión nueva, Flujo 5) o **cancelar**.
4. Si el usuario subió varios archivos y sólo algunos están duplicados, el aviso indica cuáles.

**Por qué avisar en vez de bloquear.** Re-analizar es un caso de uso legítimo — es lo que hace el equipo cuando ajusta un prompt. Bloquear el duplicado impediría el modo de trabajo principal del proyecto. Pero procesar en silencio quema tiempo y costo por accidente, así que el punto medio es avisar y dejar decidir.

### Flujo 5 — Re-análisis con correcciones previas

1. Desde un análisis existente, el usuario presiona **Re-analizar**.
2. El sistema advierte que se generará una versión nueva y que la actual se conserva.
3. Se ejecuta el análisis completo.
4. Al terminar, el sistema compara los campos que el usuario había corregido en la versión anterior con los nuevos valores, y presenta un resumen con tres casos:
   - **Coincide** — el sistema ahora extrae lo mismo que el usuario había corregido. Se informa, no requiere acción.
   - **Difiere** — el sistema extrae algo distinto de la corrección previa. Se ofrece re-aplicar la corrección, campo por campo.
   - **Sin equivalencia** — el campo corregido ya no existe en la nueva estructura. Se descarta y se informa en el resumen.
5. **Las correcciones nunca se aplican automáticamente.** El usuario decide una por una.
6. La versión anterior queda accesible desde el historial.

**Por qué campo por campo y no una comparación completa de versiones.** La comparación lado a lado es más útil para el equipo de desarrollo que evalúa si un cambio de prompt mejoró las cosas, pero es una pantalla entera y el usuario del MVP no la necesita: él quiere terminar su análisis, no auditar el sistema. Campo por campo resuelve su necesidad con una fracción del esfuerzo. La comparación de versiones queda como candidata post-MVP.

**Por qué no se aplican solas.** Porque una corrección hecha sobre la versión anterior puede haber quedado obsoleta — el usuario pudo haberla hecho sobre un dato que el sistema leyó mal por una razón que ya se corrigió. Re-aplicarla en silencio reintroduciría un valor viejo con apariencia de dato nuevo.

**Por qué se informa el caso "coincide".** Porque es la señal más directa de que el sistema mejoró, y es gratis mostrarla.

### Flujo 6 — Errores

1. **Archivo inválido** (dañado, protegido, texto ilegible): el análisis falla con el mensaje correspondiente y el archivo se conserva en el historial para descarga.
2. **Fallo de una categoría**: el análisis termina, esa categoría queda marcada como fallida y se ofrece reintentarla sola.
3. **Tiempo excedido**: a los 8 minutos se avisa que está demorando; a los 10 el análisis se detiene, se marca con error y se ofrece reintentar.

---

## 8. Límites, validaciones y mensajes

### 8.1. Límites de entrada

| Límite | Valor |
|---|---|
| Archivos por análisis | 10 |
| Tamaño por archivo | 50 MB |
| Tamaño total por análisis | 150 MB |
| Páginas por documento | 300 (con advertencia sobre 100) |
| Páginas totales por análisis | 500 |
| Formatos aceptados | PDF únicamente |

**Por qué estos valores.** Son deliberadamente generosos respecto del caso de uso descrito (pliegos de 10 a 100 páginas, promedio 30). El objetivo de un límite no es ajustarse al caso típico sino evitar el caso patológico: un usuario que arrastra una carpeta entera por error, o un documento de mil páginas que consume todo el presupuesto de procesamiento del mes. Un límite holgado no molesta a nadie y previene el desastre.

### 8.2. Cuándo se valida cada cosa

**Decisión.**
- **En el navegador, antes de subir:** formato, tamaño individual, tamaño total, cantidad de archivos.
- **En el servidor, apenas llega el archivo y antes de procesarlo:** cantidad de páginas, duplicados, integridad del PDF, protección con contraseña.

**Por qué la distinción importa.** El PRD v1.1 dice "antes de comenzar el procesamiento", que es correcto pero insuficiente. Lo que se puede validar en el navegador da feedback instantáneo y no consume ni ancho de banda ni tiempo del usuario: no tiene sentido esperar a que suban 68 MB para avisar que el máximo es 50. Lo que requiere abrir el archivo se valida en el servidor, pero **antes** de enviarlo a procesar, porque cada página procesada cuesta dinero y no conviene gastarlo en archivos que iban a ser rechazados igual.

### 8.3. Mensajes de error

**Por qué se escriben acá.** Porque si no se escriben, salen genéricos. "Formato no soportado" no le dice nada al ejecutivo que acaba de intentar subir la planilla de cotización en Excel; no sabe si el problema es el archivo, el sistema o él. Cada mensaje tiene que decir **qué archivo**, **cuál es el problema** y **qué hacer al respecto**. Escribirlos ahora cuesta media hora y ahorra una ronda de iteración con desarrollo y otra con diseño.

| Situación | Mensaje |
|---|---|
| Formato no aceptado | «{archivo}» no es un PDF. El sistema sólo analiza archivos PDF; convertí el documento antes de subirlo. |
| Archivo demasiado grande | «{archivo}» pesa {X} MB y el máximo por archivo es 50 MB. Probá comprimirlo o dividirlo en partes. |
| Total excedido | Los archivos seleccionados suman {X} MB y el máximo por análisis es 150 MB. Quitá alguno o analizalos en dos tandas. |
| Demasiados archivos | Podés subir hasta 10 archivos por análisis y seleccionaste {X}. |
| Demasiadas páginas | «{archivo}» tiene {X} páginas y el máximo es 300. Si el pliego es más extenso, dividilo y analizá las partes por separado. |
| Advertencia de extensión | «{archivo}» tiene {X} páginas. El análisis puede demorar cerca de 10 minutos. |
| PDF dañado | No se pudo abrir «{archivo}»: el archivo está dañado. Volvé a descargarlo del portal del organismo. |
| PDF protegido | «{archivo}» está protegido con contraseña. Quitale la protección y volvé a subirlo. |
| Texto ilegible | No se pudo leer el texto de «{archivo}». Puede estar escaneado con muy baja calidad. Si tenés otra copia, probá con esa; si lo escaneaste vos, repetilo a 300 DPI o más. |
| Duplicado | «{archivo}» ya fue analizado el {fecha} por {usuario}. |
| Tiempo excedido | El análisis superó los 10 minutos y se detuvo. Podés reintentarlo; si el pliego es muy extenso, probá analizando el documento principal por separado de los anexos. |
| Categoría fallida | No se pudo analizar la categoría {categoría}. El resto del análisis está completo y podés reintentar sólo esta parte. |
| Validación bloqueada | Antes de validar tenés que revisar {categorías pendientes} y resolver {X} campos en conflicto. |

---

## 9. Alcance: cambios respecto del PRD v1.1

### 9.1. Sale del MVP

- **Dashboard.** Estaba listado como funcionalidad incluida con la aclaración "nice-to-have si sobra tiempo". **Por qué sale:** eso no es alcance, es una intención, y nunca sobra tiempo. Un ítem que figura como incluido sin criterios de aceptación consume atención en todas las conversaciones de planificación y no se construye nunca. Si sobra tiempo, se agrega como historia extra.
- **Circulares con vigencia temporal** (§5.4)
- **Formatos distintos de PDF**
- **Comparación de versiones lado a lado** (Flujo 5)

### 9.2. Entra al MVP

Nada de esto estaba explícito en el PRD v1.1, y todo es necesario para que el sistema funcione como se describe:

- Datos del procedimiento como categoría de extracción (§2.1)
- Designación del documento principal (§5.1)
- Estado En conflicto y su resolución (§5.2, §5.3)
- Detección de duplicados (Flujo 4)
- Versionado de análisis y manejo de correcciones previas (§6.2, Flujo 5)
- Validación explícita de categorías críticas (§6.3, Flujo 3)
- Reintento de una categoría individual (§6.5)

### 9.3. Orden de recorte si el tiempo aprieta

1. Filtros avanzados del historial
2. Modo oscuro
3. Resaltado del texto dentro del PDF, degradando a abrir el documento en la página correcta

**Por qué ese orden.** De menor a mayor pérdida de valor. Los filtros importan recién con volumen acumulado, que no va a existir en el MVP. El modo oscuro es preferencia. El resaltado sí aporta — reduce el tiempo de verificación — pero abrir en la página correcta conserva la mayor parte del beneficio a una fracción del costo, y es además el ítem con más riesgo de estimación del proyecto.

---

## 10. Criterios de éxito del MVP

### 10.1. Por qué cambian

Los criterios del PRD v1.1 — adopción voluntaria, reducción de tiempo respecto del análisis manual, confianza del usuario — **no son medibles en este proyecto**: no hay línea de base del proceso manual, no hay usuario asignado y no hay instrumentación previa. El propio PRD lo admite: "sin mecanismo de medición actual".

Un criterio de éxito que no se puede medir no protege al proyecto, lo expone: al final alguien va a opinar si el sistema "sirvió" y no va a haber ningún dato para discutirlo. Se reemplazan por criterios que el equipo puede verificar por su cuenta.

### 10.2. Criterios de aceptación

| # | Criterio |
|---|---|
| CA-1 | Ningún campo con valor carece de una cita verificable en el documento fuente |
| CA-2 | Exactitud ≥ 85% en las tres categorías críticas, medida sobre el conjunto de referencia |
| CA-3 | Exactitud ≥ 75% en las cinco categorías restantes |
| CA-4 | Cobertura ≥ 90%: de los datos presentes en el pliego, el sistema los encuentra |
| CA-5 | Máximo 10% de "No encontrado" incorrectos en categorías críticas |
| CA-6 | El 95% de los análisis termina en 10 minutos o menos |
| CA-7 | Menos del 5% de fallos técnicos, excluyendo archivos inválidos por diseño |
| CA-8 | Los escenarios de error definidos producen el estado y el mensaje especificados |
| CA-9 | Cada dato extraído permite abrir el documento fuente en la página correcta |
| CA-10 | Cada análisis registra su costo |

**Por qué 85% y 75% y no el 90% del PRD v1.1.** Porque el 90% no tiene fundamento empírico: todavía nadie midió nada. Es un número redondo elegido antes de tener datos. Se arranca con umbrales diferenciados por criticidad y se recalibran tras la primera medición completa. **Un umbral inventado que bloquea la entrega es peor que uno honesto que se sube después.**

**Por qué la exactitud se diferencia por criticidad.** Porque el costo del error lo está. Exigir lo mismo a "Objeto y alcance" que a "Plazos clave" reparte mal el esfuerzo de ajuste.

### 10.3. Hipótesis a validar cuando haya usuario real

Se documentan; no se miden en el MVP:

- El tiempo de revisión humana se estabiliza alrededor de los 10 minutos
- El ejecutivo usa el sistema voluntariamente después de tres semanas
- El sistema detecta al menos una omisión que el análisis manual hubiera dejado pasar
- El ejecutivo basa decisiones de participación en el resultado

---

## 11. Conjunto de referencia para medir calidad

**Decisión.** Se construye de forma autónoma con pliegos públicos, sin depender de que un tercero los provea.

**Por qué.** El PRD v1.1 identifica la escasez de pliegos como su riesgo principal y lo mitiga con "solicitar más pliegos a CEDI": sin responsable, sin fecha y sin criterio de qué pliegos. Eso no es una mitigación, es una esperanza. Y es innecesaria: **los pliegos de licitación pública son documentos públicos y descargables.** El riesgo número uno del proyecto se resuelve con una tarde de trabajo y sin pedirle nada a nadie.

**Composición objetivo: 15 pliegos.** Los criterios se solapan; un pliego cuenta en varias filas.

| Criterio | Mínimo |
|---|---|
| Formato tabulado (tipo Santa Fe / Timbó) | 4 |
| Formato narrativo (tipo Municipalidad de Rosario) | 4 |
| Otros organismos / nacional | 3 |
| Documentos escaneados | 3 |
| Con anexos en archivos separados | 4 |
| Rubro informática, hardware o servicios | 8 |
| Entre 10 y 30 páginas | 5 |
| Más de 100 páginas | 3 |

**Por qué esa composición.** Cubre deliberadamente los dos extremos del espectro de formatos que el propio PRD identifica, más los casos que rompen el pipeline por razones distintas: los escaneados prueban la extracción de texto, los que tienen anexos separados prueban la lógica de unión y conflicto, y los de más de 100 páginas prueban los tiempos y los límites.

**Método:** se pre-anota con el propio sistema y se corrige a mano contra el documento. Para las tres categorías críticas la anotación se hace **sin ver la propuesta del sistema**.

**Por qué a ciegas en las críticas.** Porque revisar una respuesta ya escrita produce sesgo de aceptación: el anotador tiende a confirmar lo que ve en vez de buscar de forma independiente. En las categorías donde la medición importa más, ese sesgo inflaría artificialmente la exactitud y el número dejaría de significar algo.

**Esfuerzo:** aproximadamente 1,5 días, incluyendo recolección. Debe figurar como historia con estimación propia, no como nota al pie de un riesgo.

**Secuencia:** se arranca con los 3 pliegos disponibles y se llega a 15 antes del cierre del MVP. No bloquea el desarrollo.

---

## 12. Supuestos sin validar

El PRD v1.1 se elaboró sin contacto directo con el cliente, a partir del brief y la documentación del proceso. Los siguientes puntos son suposiciones y deben figurar como tales, **cada una con el evento que obliga a revisarla**.

| # | Supuesto | Impacto | Disparador de validación |
|---|---|---|---|
| SUP-01 | El diccionario de datos (§2.2) cubre lo que el ejecutivo necesita para decidir | Medio | Primera sesión con un ejecutivo real |
| SUP-02 | Las 7 categorías del brief son las correctas y están completas | Bajo | Primera sesión con un ejecutivo real |
| SUP-03 | El usuario prefiere ver un conflicto sin resolver antes que una resolución automática posiblemente errada | Bajo | Primera vez que un usuario se topa con un conflicto |
| SUP-04 | Mostrar la confianza como nivel es más útil que como porcentaje | Muy bajo | Primera demo |
| SUP-05 | Que todos los usuarios vean todos los análisis es aceptable | Bajo | Al superar los 3 usuarios activos |
| SUP-06 | Los pliegos no contienen información confidencial que impida procesarlos en la nube | Alto | **Antes de subir el primer pliego de una licitación privada** |
| SUP-07 | El ejecutivo sabe cuál es el documento principal al subirlo | Muy bajo | Primera sesión con un ejecutivo real |
| SUP-08 | Las circulares pueden quedar fuera del MVP | Medio | **Si aparecen en más de 3 de los 15 pliegos del conjunto de referencia** |
| SUP-09 | Los criterios de identidad de ítems (§5.3) son correctos | Medio | Al procesar los primeros pliegos con anexos separados |

**Por qué la columna de disparador.** Sin ella, una tabla de supuestos es un cementerio: se escribe una vez, se aprueba y nadie la vuelve a mirar hasta que algo se rompe. Con disparador, cada supuesto queda atado a un evento concreto que va a ocurrir de todos modos, y la revisión deja de depender de que alguien se acuerde.

**Por qué SUP-06 baja de riesgo con la decisión de §1.** Al restringir el MVP a licitaciones públicas, el único supuesto de impacto alto queda acotado a un caso que por definición no ocurre dentro del alcance.

**Nota sobre SUP-08:** se valida solo, sin cliente y sin costo adicional, mientras se arma el conjunto de referencia. Si las circulares aparecen en la mayoría de los pliegos reales, dejarlas fuera del MVP es una decisión mucho más cara de lo que parece hoy, y conviene saberlo antes de empezar y no después.

**Requisito derivado de toda esta sección.** El diccionario de datos, el vocabulario de sinónimos y los umbrales de confianza deben poder modificarse **sin reescribir el sistema**. Es lo que hace que equivocarse en cualquiera de estos supuestos cueste una edición de configuración y no un sprint. Es el requisito no funcional más importante del proyecto, precisamente porque el proyecto se está construyendo sobre suposiciones.

---

## 13. Preguntas de negocio abiertas

No se pueden resolver sin interlocutor. Deben figurar en el PRD como sección propia y visible, no escondidas entre los riesgos.

**Por qué visibles.** Un riesgo se lee como algo que podría pasar; una pregunta abierta se lee como algo que falta. Enterrar estas cinco en la sección de riesgos hace que el PRD parezca más completo de lo que está, y esa apariencia es justamente lo que impide que alguien las responda.

| # | Pregunta | Cómo se neutraliza mientras tanto |
|---|---|---|
| A-01 | ¿Cuántos pliegos se analizan por mes? ¿Cuántos usuarios en simultáneo? | El sistema se dimensiona para hasta 5 análisis simultáneos y se elimina la volumetría de los criterios de éxito |
| A-02 | ¿Cuánto tarda hoy un análisis manual y con qué tasa de error? | Se elimina como criterio de éxito. El sistema mide sus propios tiempos desde el inicio para construir la línea de base con el uso real |
| A-03 | ¿Quién paga la infraestructura y hay un techo mensual? | Se registra el costo de cada análisis desde el día uno, para que la conversación llegue con números y no con sorpresas |
| A-04 | ¿Quién es el ejecutivo que va a probar el MVP y quién es el sponsor? | "Validar el PRD con stakeholders" se reemplaza por "demo del sistema funcionando con pliegos reales" |
| A-05 | Si el sistema omite una causal de rechazo y eso genera una pérdida, ¿quién responde? | Validación obligatoria de categorías críticas, aviso visible y registro de quién validó qué. **La definición de responsabilidad sigue pendiente.** |

### 13.1. Las 8 preguntas a escalar, por retorno

1. **¿Existe hoy un formulario o checklist que el ejecutivo use para analizar pliegos?** — Valida o corrige el diccionario de datos entero de una sola vez. Es la de mayor retorno de toda la lista.
2. ¿Cuántos pliegos por mes y cuánto tarda uno?
3. ¿Alguna vez perdieron una licitación o pagaron una penalidad por una omisión?
4. De las 7 categorías, ¿cuáles 3 deciden realmente si participan?
5. ¿El alcance incluye licitaciones privadas?
6. ¿Las circulares y aclaratorias son frecuentes?
7. ¿Quién es el usuario de prueba y quién el sponsor?
8. ¿Quién paga la infraestructura?

---

## 14. Estimación

La estimación de 13 a 19 días hábiles del PRD v1.1 no contemplaba: el sistema de medición de calidad, la construcción del conjunto de referencia, el visor de documentos con ubicación y resaltado del texto, el versionado de análisis, la resolución de conflictos, ni la corrección con conservación de valores originales.

Sumado a un equipo aprendiendo la metodología y las herramientas en un proyecto real, **la estimación realista está entre dos y tres veces la original**.

**Por qué decirlo ahora.** Porque una estimación optimista escrita en un documento se convierte en un compromiso implícito, y cuando se incumple el costo no lo paga el documento sino el equipo. Corregirla en la semana cero es una conversación; corregirla en la semana cuatro es un problema.

---

## 15. Formato de los requisitos en el PRD v2

El PRD v1.1 tiene requisitos funcionales pero **no tiene criterios de aceptación**. "El sistema debe permitir subir múltiples PDF" no dice cuántos, ni qué pasa al excederse, ni cómo se verifica que está terminado.

### 15.1. Formato

```
FR-n: <enunciado>

  Criterios de aceptación:
    - Dado <contexto>, cuando <acción>, entonces <resultado observable>
    - ...

  Fuera de alcance de este requisito:
    - <lo que este requisito NO cubre>
```

**Por qué la sección "Fuera de alcance" en cada requisito y no sólo a nivel global.** Porque una lista global de exclusiones no impide que un requisito individual se infle al convertirse en historia. La expansión de alcance no ocurre a nivel documento, ocurre requisito por requisito, y ahí es donde hay que contenerla. **Ningún requisito se considera terminado sin esa sección, aunque diga "ninguno".**

### 15.2. Ejemplos calibrados

Estos tres ejemplos fijan el nivel de detalle esperado. Están tomados de los requisitos más difíciles a propósito: si el resto sale a esta altura, el PRD queda implementable.

---

**FR-A: Visualización y resolución de campos en conflicto**

```
Criterios de aceptación:
- Dado un análisis donde el documento principal indica 5% de garantía de
  cumplimiento y un anexo indica 10%, cuando el usuario abre la categoría
  Garantías, entonces ve ambos valores, cada uno con su documento de origen
  y su cita, y el ítem marcado como "En conflicto".
- Dado un listado donde el documento principal aporta 4 requisitos y el anexo
  aporta 6 requisitos distintos, cuando el usuario abre la categoría, entonces
  ve los 10 requisitos en un solo listado, cada uno indicando su documento de
  origen, y ningún ítem marcado como conflicto.
- Dado un campo en conflicto, cuando el usuario selecciona uno de los dos
  valores, entonces el ítem pasa a estado "Extraído", queda registrado que fue
  resuelto manualmente y el valor descartado se conserva.
- Dado un análisis con al menos un campo en conflicto sin resolver, cuando el
  usuario intenta validar el análisis, entonces el sistema lo impide e indica
  cuántos conflictos quedan pendientes, con acceso directo a cada uno.

Fuera de alcance de este requisito:
- El sistema no determina cuál de los dos valores es el correcto
- No existe orden de prelación automático entre documentos
- No se detectan conflictos entre análisis distintos del mismo pliego
```

---

**FR-B: Re-análisis con correcciones previas**

```
Criterios de aceptación:
- Dado un análisis existente en versión 1, cuando el usuario presiona
  Re-analizar y confirma, entonces se crea la versión 2 y la versión 1 sigue
  accesible desde el historial.
- Dado que en la versión 1 el usuario corrigió el porcentaje de garantía de
  5% a 8%, cuando termina la versión 2 y el sistema extrae 8%, entonces el
  resumen informa que el nuevo valor coincide con la corrección previa y no
  solicita ninguna acción.
- Dado el mismo caso, cuando la versión 2 extrae 6%, entonces el sistema
  ofrece re-aplicar la corrección previa para ese campo, mostrando ambos
  valores, y no la aplica hasta que el usuario lo confirme.
- Dado que un campo corregido en la versión 1 no tiene equivalente en la
  estructura de la versión 2, cuando termina el re-análisis, entonces esa
  corrección se descarta y se informa en el resumen.
- Dado un re-análisis en curso, cuando el usuario consulta el historial,
  entonces la versión 1 sigue disponible y marcada como versión anterior.

Fuera de alcance de este requisito:
- No hay comparación lado a lado entre versiones
- Las correcciones no se aplican automáticamente en ningún caso
- No se pueden combinar campos de dos versiones distintas en un resultado
```

---

**FR-C: Validación de un análisis**

```
Criterios de aceptación:
- Dado un análisis completado donde el usuario no revisó ninguna categoría
  crítica, cuando presiona Validar análisis, entonces el sistema lo impide e
  indica cuáles de las tres categorías críticas faltan revisar.
- Dado un análisis donde el usuario revisó las tres categorías críticas y no
  quedan conflictos, cuando presiona Validar análisis, entonces el análisis
  pasa a estado Validado y queda registrado quién lo validó y cuándo.
- Dado que el usuario hizo scroll sobre una categoría crítica sin marcarla
  como revisada, cuando intenta validar, entonces esa categoría sigue contando
  como pendiente.
- Dado un análisis ya validado, cuando el usuario corrige el valor de un campo,
  entonces el análisis vuelve a estado no validado y debe validarse de nuevo.

Fuera de alcance de este requisito:
- No hay aprobación por parte de un segundo usuario
- La validación no bloquea la edición posterior
- El sistema no evalúa si la decisión de participar es correcta
```

---

**Por qué estos tres y no otros.** Concentran los tres mecanismos nuevos y más difíciles de especificar: la lógica de conflicto y unión, el manejo del estado entre versiones, y el control de validación. Son los requisitos donde un criterio de aceptación vago produce la implementación más equivocada.

---

## 16. Estructura del PRD v2

### 16.1. Sacar del PRD

Van al documento de arquitectura:

- Sección 4 completa: Arquitectura y Stack Técnico, incluido el árbol de directorios
- Sección 10 completa: Dependencias y Decisiones Técnicas Pre-tomadas
- Toda mención de servicios, frameworks y librerías dentro de los requisitos funcionales

**Nota sobre una contradicción del PRD v1.1.** La sección 10 declara decisiones que "no deben replantearse", y los próximos pasos proponen ejecutar la fase de arquitectura. Si están cerradas, esa fase es ceremonial; si no lo están, la sección 10 no dice la verdad. Al separar los documentos la contradicción desaparece: el PRD dice **qué** hace el sistema y el documento de arquitectura dice **cómo**, y ahí las decisiones ya tomadas entran con su justificación.

**Al migrarlas, conviene fusionar las secciones 4 y 10:** hoy se solapan bastante y arrastrarlas tal cual duplica el contenido.

### 16.2. Agregar al PRD

- Apéndice: diccionario de datos de las 8 categorías (§2.2)
- Sección: estados de un campo y sus reglas (§3)
- Sección: flujos (§7) — reemplaza el escenario único de §2.3 del PRD v1.1
- Apéndice: mensajes de error (§8.3)
- Sección: supuestos con su disparador de validación (§12)
- Sección: preguntas de negocio abiertas (§13)
- Sección: conjunto de referencia (§11)

### 16.3. Eliminar del PRD

- NFR-1.2 "cero falsos positivos" → reemplazado por §4.1
- NFR-1.3 "menos del 10% de campos en revisión manual" → ver §4.3
- Sección 7 completa (Criterios de Éxito) → reemplazada por §10
- Dashboard de la lista de funcionalidad incluida → pasa a No incluido

### 16.4. Regla final

En el documento resultante no debe quedar ninguna frase con "TBD", "a definir", "según necesidad real" ni "[ASSUMPTION]" sin resolver.

**Por qué.** El PRD v1.1 tiene seis marcas de supuesto explícitas y alrededor de quince ambigüedades implícitas. Cada hueco que quede abierto lo va a llenar el agente de desarrollo con una invención distinta, y esas invenciones no van a ser consistentes entre sí porque cada historia se genera por separado. Un supuesto explícito y documentado se puede corregir en un lugar; quince invenciones dispersas hay que ir a buscarlas.
