# Auditoría RAG — licitaciones-pi

**Fecha:** 2026-08-13
**Alcance:** pipeline completo de extremo a extremo (ingestion → chunking → indexing → retrieval → context → synthesis → attribution → highlighting)
**Regla aplicada:** ningún archivo fue modificado. Todos los hallazgos están verificados contra el código real; los que no pude confirmar del todo están marcados explícitamente como *hipótesis a confirmar* y separados al final.

---

## Resumen ejecutivo

Encontré **28 hallazgos verificados** (5 críticos, 11 altos, 9 medios, 3 bajos) y 4 hipótesis a confirmar.

Los tres que, en mi lectura, explican la mayor parte de la diferencia entre lo que el sistema *cree* que hace y lo que el usuario *ve*:

1. **HL-01** — el cálculo de coordenadas de highlight invierte verticalmente el eje Y. **Todos** los resaltados que se calculan por el camino primario (PyMuPDF en vivo) se dibujan espejados respecto de su posición real. Lo reproduje: un texto a 78pt del tope de una página A4 se emite con `y=749`, o sea a 671pt de error sobre 842pt de página.

2. **SYN-02** — si el LLM de síntesis no reproduce sus evidencias con exactitud literal, la narrativa entera de la categoría se descarta y el usuario ve *"No se encontró información sobre Garantías en los documentos del pliego"* aunque la extracción haya encontrado y verificado los datos. No hay fallback al camino `item_refs`.

3. **IDX-01 + RET-02** — BM25 solo puede matchear `content` y `title`; el `content` se guarda deliberadamente sin el encabezado, y `heading_path`/`section_path` están declarados no-searchable. Encima, la query de keywords que alimenta BM25 sale del glossary **sin acentos** mientras que el texto indexado los conserva, y no hay ningún analizador español configurado en el repo. El 41% de los términos del glossary contiene al menos una palabra que en castellano real lleva tilde.

Sobre tu pregunta central (capa 7): **sí, los cuatro conceptos colapsan**, pero no en un solo lugar — colapsan en tres lugares distintos y por razones distintas. El detalle está en la sección de la Capa 7.

---

# CAPA 1 — Ingestion / extraction

### ING-01 · crítica · Desalineación del índice de bbox por párrafos de membrete/pie

**Evidencia** — `backend/extraction/document_intelligence.py:238-263`

```python
paras_by_page: dict[int, list] = {}
for para in paragraphs:                       # ← TODOS los paragraphs, sin filtrar por role
    page = _first_page_number(para)
    ...
for page_num, page_paras in paras_by_page.items():
    for idx, para in enumerate(page_paras_sorted):
        para_id = (page_num, idx)             # ← identidad = posición secuencial
        bbox_index[para_id] = bboxes
```

y `document_intelligence.py:433-437`

```python
if _MD_COMMENT_RE.match(stripped):
    # <!-- PageNumber=... / PageFooter=... / PageHeader=... --> ... se descarta
    continue
```

**Qué debería pasar** — el bloque *i* del parser de markdown debe corresponder al párrafo *i* de `result.paragraphs` en esa página, porque el bbox se busca por índice posicional.

**Qué pasa** — `DocumentParagraph` de Azure DI expone un atributo `role` (lo verifiqué contra el SDK instalado) que vale `pageHeader`, `pageFooter`, `pageNumber`, `footnote`, etc. Esos párrafos **sí están** en `result.paragraphs` y por lo tanto ocupan índices en `bbox_index`, pero en el markdown salen como comentarios HTML y el parser los descarta. El resultado es un corrimiento de índices.

**Escenario de falla** — un pliego con membrete del organismo en cada página (el caso normal, no el borde). En la página 7, el índice 0 de `bbox_index` es el membrete y el índice 1 el primer párrafo real; el bloque 0 del parser es el primer párrafo real. Todos los bloques de esa página reciben el bbox del párrafo **anterior**. El usuario hace clic en una cita de "GARANTÍAS" y el visor resalta el párrafo de arriba. Si hay membrete *y* pie, el corrimiento es de dos.

**Nota importante de alcance** — en producción este bbox es el camino de *fallback* (ver HL-05), así que hoy el impacto queda amortiguado. Pero es el camino que se usa cada vez que PyMuPDF no encuentra la cita, y el bug de ING-01 es la razón por la que ese fallback tampoco salva la situación.

**Fix propuesto** — filtrar por `role` al construir el índice: excluir `pageHeader`, `pageFooter`, `pageNumber`. Mejor aún: dejar de emparejar por índice posicional y emparejar por `spans[0].offset`, que es una identidad real y no una convención frágil entre dos parsers independientes.

---

### ING-02 · media · `span` vs `spans`: el ordenamiento determinístico no existe

**Evidencia** — `backend/extraction/document_intelligence.py:252-255`

```python
page_paras_sorted = sorted(
    page_paras,
    key=lambda p: getattr(getattr(p, "span", None), "offset", 0)
)
```

**Verificación** — instalé `azure-ai-documentintelligence` y comprobé:

```
DocumentParagraph.__annotations__ → ['spans']
has span attr: False | has spans: False (es un TypedDict; la key es 'spans')
```

`getattr(p, "span", None)` devuelve siempre `None` y la key de ordenamiento es la constante `0` para todos los párrafos. El `sorted` es un no-op.

**Confirmación cruzada** — en el mismo archivo, `_first_span_offset` (`:116-122`) usa `getattr(item, "spans", None)` correctamente. Es un typo, no una decisión.

**Qué pasa hoy** — como `sorted` es estable y Azure devuelve los párrafos en orden de lectura, el resultado *casualmente* es correcto. Pero la garantía que promete el comentario ("orden determinístico") no está implementada, y cualquier cambio futuro en el orden de entrada rompe silenciosamente el mapeo de bbox de todo el documento.

**Fix propuesto** — `key=lambda p: (getattr(p, "spans", None) or [{}])[0].get("offset", 0)`. Y agregar un test que verifique el orden con párrafos deliberadamente desordenados.

---

### ING-03 · media · Validación de bbox con límites hardcodeados, ciega a la unidad

**Evidencia** — `backend/extraction/document_intelligence.py:344-357`

```python
if (
    0 <= bbox["x"] <= 1200
    and 0 <= bbox["y"] <= 1600
    and 0 < bbox["width"] <= 1200
    and 0 < bbox["height"] <= 1600
):
    valid_bboxes.append(bbox)
else:
    logger.warning("bbox_out_of_bounds", ...)
```

**Qué pasa** — Azure DI expone la unidad de coordenadas en `result.pages[i].unit`: **pulgadas** para PDF, **píxeles** para imagen. El código nunca la lee. Para un PDF los valores son del orden de 1–11 y la validación nunca dispara. Para un documento escaneado indexado como imagen a 300 DPI (A4 = 2480×3508 px) **todos** los bbox caen fuera de rango y se descartan.

**Escenario de falla** — un pliego escaneado (habitual en municipios). Se loguea un `bbox_out_of_bounds` por párrafo, `block["bbox"] = []` para todo el documento, y el fallback de highlighting queda inutilizado sin que nada falle ruidosamente.

**Fix propuesto** — leer `result.pages[i].unit` y normalizar a una unidad única (o a fracción de página, usando `page.width`/`page.height`), y validar contra las dimensiones reales de la página en vez de contra dos constantes.

---

### ING-04 · media · Las filas de una tabla que cruza páginas heredan la página de la primera

**Evidencia** — `backend/extraction/document_intelligence.py:180` y `:201-214`

```python
table_page = _first_page_number(table)
...
row_blocks.append({
    "page_number": table_page,      # ← igual para TODAS las filas
    ...
    "bbox": bboxes_by_row.get(row_index, []),   # ← el bbox SÍ trae la página real de cada celda
})
```

**Qué pasa** — una tabla que arranca en la página 3 y sigue en la 4 registra todas sus filas como página 3, mientras que cada `bbox` interno declara su página real. El chunk queda internamente contradictorio.

**Escenario de falla** — un cronograma de hitos en una tabla que cruza el salto de página. El usuario hace clic en la cita del hito de la página 4; el visor abre la página 3 (`source.page_number`) y el filtro `bbox_item.get("page") == page_number` de `highlight.py:538` no matchea ningún bbox, así que tampoco resalta nada. Doble falla: página equivocada y sin resaltado.

**Fix propuesto** — asignar `page_number` por fila usando la página del primer bbox de esa fila, con fallback a `table_page`.

---

### ING-05 · baja · El perfil "development" documentado no existe en el código

**Evidencia** — `.env.example:22-32` documenta un perfil completo:

```
# Development profile (APP_ENV=development)
# Ingestion: MarkItDown
# Embeddings: Sentence Transformers (BAAI/bge-m3)
# Vector store: ChromaDB
# LLM: Cohere
MARKITDOWN_ENABLED=true
SENTENCE_TRANSFORMERS_MODEL=BAAI/bge-m3
CHROMA_PERSIST_DIRECTORY=./local_blob_storage/chroma
COHERE_API_KEY=
```

Contra `backend/shared/config.py:102-104`:

```python
# FIX: Dead code eliminado (#1, #2, #3) - campos legacy de adaptadores locales:
# - cohere_api_key, cohere_model (solo para CohereAdapter local)
# - sentence_transformers_model, chroma_persist_directory (solo para Chroma local)
```

Un grep por `markitdown|chroma|cohere|sentence_transformer` en todo `backend/` no devuelve una sola implementación. `document_intelligence.py:645-655` tira `DocumentTextExtractionError` si falta la config de Azure DI — no hay fallback.

**Por qué importa** — no es un bug de runtime, pero es la razón por la que arrancaste esta auditoría preguntando por "el fallback a MarkItDown". Cualquiera que lea el `.env.example` va a razonar sobre un sistema que no existe.

**Fix propuesto** — borrar el bloque del perfil development del `.env.example`, o reetiquetarlo como histórico.

---

# CAPA 2 — Chunking

### CHK-01 · crítica · Chunks de hasta 2× el tamaño configurado, con duplicación total del contenido

**Evidencia** — `backend/extraction/chunking.py:204-220`

```python
if current and current_tokens + len(tokens) > chunk_size:
    chunks.append("\n\n".join(current))
    carried: list[str] = []
    carried_tokens = 0
    for prev_paragraph in reversed(current):
        prev_tokens = len(_tokenize(prev_paragraph))
        if carried and carried_tokens + prev_tokens > overlap:   # ← 'if carried' hace que
            break                                                #   el 1er párrafo entre SIEMPRE
        carried.insert(0, prev_paragraph)
        carried_tokens += prev_tokens
        if carried_tokens >= overlap:
            break
    current = carried
    current_tokens = carried_tokens

current.append(paragraph)          # ← se appendea SIN volver a chequear el límite
current_tokens += len(tokens)
```

**Reproducción** (ejecuté la función tal cual, con los defaults `chunk_size=700, overlap=120`):

```
Entrada: 3 párrafos de 690 tokens (2070 tokens totales)
Salida:  3 chunks de 690, 1380 y 1380 tokens (3450 tokens emitidos)
  chunk 0: a0 → a689
  chunk 1: a0 → b689     ← contiene ÍNTEGRAMENTE al chunk 0
  chunk 2: b0 → c689
Redundancia: 67%
```

Caso típico (8 párrafos de 200 tokens):

```
Entrada: 1600 tokens → Salida: 2200 tokens en 4 chunks [600,600,600,400]
Overlap real: 200 tokens (un párrafo entero) en vez de los 120 configurados. +37%
```

**Qué debería pasar** — chunks de a lo sumo `chunk_size` tokens, con `overlap` tokens de solapamiento.

**Qué pasa** — el carry de overlap arrastra siempre al menos un párrafo completo (por el `if carried` de la línea 210), y después se appendea el párrafo que disparó el flush sin revalidar el límite. Con párrafos > `chunk_size/2` el chunk resultante duplica exactamente al anterior.

**Escenario de falla** — un artículo de pliego con dos párrafos largos de considerandos. Se generan dos chunks casi idénticos. Ambos matchean la misma query, ambos entran en el top-k, y el LLM ve el mismo texto dos veces: eso infla artificialmente la señal de "dato consistente en múltiples fragmentos" (que el prompt del sistema premia con **+0.2 de confidence**, `_base_system.txt:86`). El sistema se auto-confirma con una copia de sí mismo. Además infla el conteo de chunks, que es lo que hace que el tope de 1000 de SYN-05 se alcance antes.

**Fix propuesto** — dos cambios independientes: (a) en el carry, no arrastrar un párrafo si por sí solo excede `overlap`; (b) después del carry, si `carried_tokens + len(tokens) > chunk_size`, emitir el carry como chunk propio o descartarlo antes de appendear. Test de regresión: ningún chunk emitido puede superar `chunk_size`, y ningún chunk puede ser substring de otro.

---

### CHK-02 · alta · Todas las piezas de un bloque partido declaran los bbox de todo el bloque

**Evidencia** — `backend/extraction/chunking.py:1254-1280` (dentro del `for chunk_content in content_pieces:`)

```python
for chunk_content in content_pieces:
    ...
    merged_blocks = block.get("merged_blocks", [])     # ← el mismo para TODAS las piezas
    blocks_data = [
        {"para_id": mb.get("para_id"), "page": page_number,
         "bbox": mb.get("bbox", []), "content": mb.get("content", "")}
        for mb in merged_blocks
    ] if merged_blocks else [...]

    source = {"page": page_number, "block_type": "paragraph", "blocks": blocks_data}
```

**Qué pasa** — `_merge_intermediate_blocks` fusiona N párrafos en un bloque y guarda sus `merged_blocks` (para_id + bbox de cada uno). `_split_block_into_chunks` vuelve a partir ese bloque en M piezas. Pero cada pieza recibe la lista **completa** de los N `merged_blocks`, sin filtrar cuáles de esos párrafos están efectivamente en esa pieza.

**Escenario de falla** — una sección con 5 párrafos que se fusiona y luego se parte en 2 chunks. El chunk 2 (párrafos 3-5) declara como fuente los bbox de los 5. Cuando el fallback de highlighting recorre `source.blocks` buscando cuál contiene la cita, el filtro por contenido de `highlight.py:502-516` lo salva **si** la cita está bien; pero el `source` persistido en el índice miente igual, y cualquier consumidor que no filtre (el `blocks_data` legacy, la telemetría, un futuro consumidor) obtiene la región equivocada.

**Fix propuesto** — filtrar `merged_blocks` por cada pieza: quedarse solo con los `mb` cuyo `content` esté contenido en `chunk_content`. Es un chequeo barato y ya existe la misma lógica normalizada en `highlight.py`.

---

### CHK-03 · alta · Los chunks `child` heredan el `source` del `parent` por referencia

**Evidencia** — `backend/extraction/chunking.py:1329-1338`

```python
child_dict = {
    **chunk_dict,                       # ← copia SUPERFICIAL: 'source' y 'blocks'
    "chunk_index": chunk_index,         #    quedan apuntando al MISMO objeto del parent
    "content": child_content,
    "token_count": len(_tokenize(child_content)),
    "title": f"{title}.{inciso_label}" if title else inciso_label,
    "section_path": f"{section_path} > {inciso['label']}",
    "chunk_type": "child",
    "parent_chunk_index": parent_index,
}
```

**Qué debería pasar** — todo el punto de parent/child es que el child sea *más preciso*: el retrieval matchea el inciso puntual y el highlight debería marcar ese inciso.

**Qué pasa** — el `source` del child es el del parent: los bbox de todos los párrafos del artículo completo. Y como `{**chunk_dict}` es shallow, es literalmente el mismo dict en memoria (una mutación en uno se propaga a todos).

**Escenario de falla** — "Artículo 14: Documentación a presentar. a) … b) constituir garantía de mantenimiento de oferta del 1% … c) …". El child del inciso b) es el que matchea la query de garantías, pero al citarlo el visor resalta el artículo 14 entero, incluyendo los incisos a) y c) que hablan de otra cosa. El usuario ve un resaltado de media página para un dato de una línea.

**Fix propuesto** — recortar `source.blocks` del child a los bloques cuyo contenido intersecte con `inciso["text"]`, y hacer `copy.deepcopy` (o reconstruir el dict) en vez de spread superficial.

---

### CHK-04 · alta · Código muerto con pérdida de información: los headings sin cuerpo nunca llegan a ser chunk

**Evidencia** — `backend/extraction/chunking.py:669-683` construye deliberadamente bloques puro-encabezado:

```python
def pop_to_level(level: int, page_number: int) -> None:
    while heading_stack and heading_stack[-1][1] >= level:
        text, _popped_level = heading_stack.pop()
        had_body = heading_has_body.pop()
        if not had_body:
            intermediate.append({
                "page_number": page_number, "block_type": "paragraph",
                "content": "", "table_ref": None,
                "heading_path": current_path() + [text],
                "is_heading": True,
            })
```

con el docstring (`:641-643`): *"Un encabezado que nunca recibe ningún parrafo/tabla propio antes de cerrarse (ej. la portada de un anexo que es solo un titulo) igual se conserva como su propio bloque puro-encabezado, para no perderlo."*

Y `chunking.py:1245-1252`:

```python
body = "" if block.get("is_heading") else str(block["content"]).strip()

if body:
    content_pieces = _split_block_into_chunks(body, chunk_size, overlap)
else:
    # Heading sin body → crear chunk vacío con metadata (poco común)
    content_pieces = []          # ← lista vacía: el for de abajo no ejecuta nunca
```

**Qué pasa** — el bloque llega con `content=""` y `is_heading=True`, `body` queda `""`, `content_pieces` queda `[]`, y el `for chunk_content in content_pieces:` no itera. **No se emite ningún chunk.** El comentario de la línea 1251 dice "crear chunk vacío con metadata" y no crea nada. Toda la maquinaria de `heading_has_body` es código muerto.

**Escenario de falla** — la carátula de "ANEXO III — DECLARACIÓN JURADA DE APTITUD PARA CONTRATAR" que es solo un título con el formulario en la página siguiente bajo otro heading. Ese anexo simplemente **no existe** en el índice. La categoría `anexos_obligatorios` no lo puede recuperar y el sistema reporta que el pliego no lo pide.

**Fix propuesto** — emitir el chunk con `content = heading_path[-1]` (el texto del título) en vez de `""`. Es el único caso donde el heading debe ir al `content`, precisamente porque no hay cuerpo que lo represente.

---

### CHK-05 · alta · `identificacion_procedimiento` es el tacho de basura de la clasificación

**Evidencia** — `backend/extraction/chunking.py:1110-1113`

```python
# Fallback final: si aún no hay categoría, asignar "identificacion_procedimiento"
# como default genérico (es la categoría menos específica)
if not primary_category:
    primary_category = "identificacion_procedimiento"
```

**Qué pasa** — todo chunk sin heading reconocible y sin suficiente densidad de keywords termina etiquetado `identificacion_procedimiento`. En un pliego típico eso es la mayoría del texto de relleno (considerandos, remisiones normativas, formalidades).

**Impacto concreto en retrieval** — `_retrieve_with_category_priority` (`extractors/base.py:988-997`) aplica un boost de +20% a los chunks cuya `primary_category` coincide con la categoría objetivo. Al extraer `identificacion_procedimiento`, **casi todo el ruido del documento recibe el boost**, compitiendo con la carátula real.

**Escenario de falla** — un pliego cuya carátula está en una tabla (que además, por CHK-06, se clasifica por el heading del ancestro). La categoría "Identificación del procedimiento" devuelve considerandos jurídicos boosteados en vez de la carátula, y el número de expediente sale de `_augment_identificacion_payload` (el regex de rescate) en vez del LLM — con `confidence: 0.78` hardcodeado (`base.py:756`).

**Fix propuesto** — usar `primary_category = None` y dejar que el chunk sea "sin categoría". El boost por categoría no necesita que todo chunk tenga una; un chunk sin categoría simplemente no recibe boost, que es exactamente el comportamiento deseado.

---

### CHK-06 · alta · El heading ancestro le gana a la sección real en la clasificación

**Evidencia** — `backend/extraction/chunking.py:918-947`

```python
heading_text = " ".join(heading_path).lower()      # ← concatena ANCESTROS + hoja
normalized = _normalize_for_matching(heading_text)

for category, patterns in CATEGORY_HEADING_PATTERNS.items():
    matches = 0
    earliest = len(normalized)
    for pattern in patterns:
        position = normalized.find(_normalize_for_matching(pattern))
        if position >= 0:
            matches += 1
            earliest = min(earliest, position)
    if matches > 0:
        scores[category] = (matches, earliest)

# Mayor cantidad de matches; a igualdad, el que aparece primero.
return min(scores.items(), key=lambda item: (-item[1][0], item[1][1]))[0]
```

**Qué pasa** — el desempate `earliest` favorece estructuralmente al ancestro, porque los ancestros van primero en el string concatenado.

**Escenario de falla concreto** — `heading_path = ["LICITACIÓN PÚBLICA Nº 5/2026", "GARANTÍAS"]`:

- `identificacion_procedimiento` matchea `"licitacion"` en la posición 0 → `(1, 0)`
- `garantias` matchea `"garantia"` en la posición ~26 → `(1, 26)`
- Empate en matches → gana `earliest` → **`identificacion_procedimiento`**

Toda la sección de garantías de ese pliego queda clasificada como identificación del procedimiento. Y como el título tiene prioridad absoluta sobre las keywords (`:1076`, `primary_category = heading_category`), el contenido —que está lleno de "caución", "póliza", "mantenimiento de oferta"— no puede corregirlo.

Esto es, muy probablemente, la causa raíz de lo que describís como "dos pliegos equivalentes se comportan distinto": depende de si el organismo repite el nombre del llamado en el encabezado de sección o no.

**Fix propuesto** — clasificar solo por el heading hoja (`heading_path[-1]`), o ponderar los ancestros con un peso decreciente. El desempate por posición debería ser *dentro* del heading hoja, no a lo largo de toda la ruta.

---

### CHK-07 · media · Matching de términos multi-palabra por subconjunto, sin orden ni adyacencia

**Evidencia** — `backend/extraction/chunking.py:983-987`

```python
normalized_term = _normalize_for_matching(str(term))
term_tokens = set(normalized_term.split())
if term_tokens.issubset(content_tokens):
    matches += 1
```

**Qué pasa** — el término `"mantenimiento de oferta"` se descompone en `{mantenimiento, de, oferta}` y matchea si las tres palabras aparecen **en cualquier lugar del chunk, en cualquier orden**. La palabra `"de"` está en el 100% de los chunks en castellano.

**Escenario de falla** — un chunk sobre servicios: *"El adjudicatario será responsable del mantenimiento preventivo de los equipos durante toda la vigencia. La oferta económica deberá contemplar…"*. Matchea `"mantenimiento de oferta"` (garantías) y probablemente también `"oferta economica"` (criterios). Con solo 2-3 de estos falsos matches y un chunk corto, CHK-08 lo convierte en `primary_category` de garantías.

**Fix propuesto** — para términos multi-palabra, buscar la frase normalizada como substring (`normalized_term in normalized_content`) en vez de subconjunto de tokens. Es más barato y estrictamente más preciso.

---

### CHK-08 · media · La fórmula de densidad hace lo contrario de lo que documenta, y satura con un solo match

**Evidencia** — `backend/extraction/chunking.py:1015-1023`

```python
term_coverage = min(match_count / _KEYWORD_SCORE_SATURATION, 1.0)   # SATURATION = 4

# Density: ... Normalizado por cada 100 palabras para evitar penalizar chunks largos
words_per_100 = max(content_length / 100.0, 1.0)
keyword_density = min(match_count / words_per_100, 1.0)

score = term_coverage * keyword_density * category_weight
```

**Dos problemas verificados:**

1. **El comentario miente.** `keyword_density = match_count / (len/100)` es *inversamente* proporcional a la longitud. Un chunk de 700 palabras con 4 matches da `4/7 = 0.57`; uno de 100 palabras con 4 matches da `1.0`. Penaliza chunks largos, que es exactamente lo que dice evitar.

2. **El piso `max(..., 1.0)` satura cualquier chunk corto.** Para `content_length < 100`, `words_per_100 = 1.0` y `keyword_density = min(match_count, 1.0) = 1.0` con un solo match. Entonces `score = (1/4) * 1.0 * 1.0 = 0.25`, que es **exactamente** `_DEFAULT_PRIMARY_THRESHOLD` (`:67`).

**Escenario de falla** — una fila de tabla o un párrafo corto (< 100 palabras) que menciona una sola vez la palabra "anexo" alcanza el umbral primario de su categoría con el default. Combinado con CHK-07 (matches falsos fáciles), la clasificación de chunks cortos es esencialmente aleatoria. Las tablas —que en pliegos son cronogramas y planillas de cotización, o sea alto valor— son mayoritariamente chunks cortos.

**Fix propuesto** — sacar el piso `max(..., 1.0)` y usar un mínimo de longitud para la normalización (p. ej. `max(content_length, 50)/100`), o directamente medir densidad como `match_count / total_tokens` y calibrar los umbrales contra un set de chunks etiquetados a mano.

---

### CHK-09 · media · Fusión de headings partidos sin espacio y con un disparador demasiado laxo

**Evidencia** — `backend/extraction/chunking.py:494` y `:508-522`

```python
next_starts_lowercase = first_word_next[0].islower()
...
is_fragmented = (
    next_starts_lowercase or            # ← disparador único, sin más condiciones
    next_starts_with_short_fragment or
    likely_continuation
)

if is_fragmented:
    merged_content = content + next_content     # ← SIN espacio
```

**Qué pasa** — para el caso real que motivó la función (`"ARTÍCULO 12: PLA"` + `"ZO DE ENTREGA"`) la concatenación sin espacio es correcta. Pero `next_starts_lowercase` dispara también cuando el heading de la página N+1 es un heading legítimo que arranca en minúscula.

**Escenario de falla** — página N: heading `"5. GARANTÍAS"`; página N+1: heading `"de cumplimiento de contrato"` (Azure DI parte así los títulos en dos renglones tipográficos con bastante frecuencia). Resultado: `"5. GARANTÍASde cumplimiento de contrato"`. El token `garantiasde` no existe, y `_classify_by_heading` busca `"garantia"` por substring — que *sí* matchea, porque es prefijo. Pero el `title` que va al embedding y al campo searchable del índice queda corrupto, y `_normalize_heading_value` no lo arregla.

**Fix propuesto** — unir con `""` solo cuando el fragmento siguiente sea corto y en mayúsculas (el caso `"ZO"`); en el caso `next_starts_lowercase`, unir con `" "`. Y exigir además que el heading actual **no** termine en un token que sea una palabra completa del diccionario, para no fusionar dos headings legítimos.

---

# CAPA 3 — Indexación (Azure AI Search)

### IDX-01 · crítica · BM25 no puede ver los encabezados

**Evidencia** — tres piezas que juntas cierran el problema:

`backend/scripts/migrate_search_index_add_markdown_heading_fields.py:62-66`
```python
"heading_path": SearchField(
    ...
    searchable=False,
),
```

`backend/scripts/migrate_search_index_add_chunk_fields.py:55`
```python
"section_path": SimpleField(name="section_path", type=SearchFieldDataType.String, filterable=False),
```
(`SimpleField` implica `searchable=False`.)

`backend/extraction/ai_search.py:232-234`
```python
# RAG ARCHITECTURE: content es PURO (sin títulos)
# Embedding ya fue generado con contexto (title + content)
"content": chunk["content"],
```

**Qué pasa** — el único campo searchable con el texto del encabezado es `title` (`update_azure_search_schema.py:50-58`), que contiene **solo el heading hoja**. Todo el resto de la ruta jerárquica es invisible para BM25.

**Escenario de falla** — un pliego que titula la sección `"CAPÍTULO IV — DE LAS GARANTÍAS"` y dentro tiene subsecciones `"4.1 Constitución"`, `"4.2 Devolución"`. El chunk de 4.1 tiene `title = "4.1 Constitución"` y un `content` que dice *"deberá constituirse por el 1% del monto, mediante alguna de las formas previstas en el artículo 100"* — sin la palabra "garantía". La query de keywords de la categoría garantías no lo matchea por BM25. Solo lo puede recuperar el lado vectorial, que sí ve `title + content` (`embeddings.py:134`) pero tampoco ve `"CAPÍTULO IV — DE LAS GARANTÍAS"`.

Este es exactamente el escenario que planteaste: *"encabezados que no aparecen literalmente en el texto del chunk y por lo tanto no matchean por keyword"*. Está confirmado.

**Fix propuesto** — declarar `section_path` como `SearchableField` con analizador español, e incluir el `section_path` completo (no solo el `title` hoja) en el input del embedding. Requiere reindexar.

---

### IDX-02 · crítica · Ningún analizador español, y una query de keywords sin acentos

**Evidencia** — el repo entero no configura un solo analizador. `update_azure_search_schema.py:50-58` crea `title` sin parámetro `analyzer`, y `scripts/update_azure_search_schema.ps1:90-92` y `:112-114` lo hacen explícito:

```powershell
indexAnalyzer = $null
searchAnalyzer = $null
analyzer = $null
```

Un grep por `analyzer|SemanticConfiguration|query_type|rerank|ScoringProfile` en todo el repo devuelve **solo** esas líneas del `.ps1`.

Del otro lado, `analysis/extraction/glossary.py:41-51`:

```python
def build_keyword_query(category_key: str) -> str:
    """Construye una query de keywords para BM25: solo los términos
    discriminantes del glossary, sin oraciones largas ni stopwords."""
    ...
    return " ".join(terms)
```

Y los términos del glossary están escritos **sin tildes**. Lo cuantifiqué sobre `glossary.json`:

```
términos totales: 213
con al menos una palabra que en castellano real lleva tilde: 87 (41%)
ejemplos: "descripcion de la contratacion", "plazo de ejecucion",
          "condiciones de admision", "capacidad tecnica",
          "objeto de la licitacion", "inscripcion registro proveedores"
```

**Qué pasa** — sin analizador declarado, Azure usa `standard.lucene`: tokeniza, pasa a minúsculas y aplica una lista de stopwords en **inglés**. No hace *stemming* ni *accent folding*. Entonces el token indexado `garantía` y el término de búsqueda `garantia` son términos distintos, y `plazos` no matchea `plazo`.

**La inconsistencia interna que lo hace evidente**: el mismo glossary se usa en dos lugares. En `chunking.py::_count_keyword_matches` se normalizan **ambos lados** con `_normalize_for_matching` (que quita acentos), así que la clasificación funciona. En `build_keyword_query` los términos van crudos a Azure, donde nada los normaliza. Un mismo glossary, dos semánticas.

**Escenario de falla** — la categoría `garantias` manda a BM25 la query `"garantia garantia de oferta mantenimiento de oferta ... caucion fianza ... poliza ..."`. Contra un pliego que escribe "garantía", "caución" y "póliza" con tilde (o sea, cualquier pliego bien redactado), el aporte léxico de esos términos a la fusión RRF es cero. El sistema queda dependiendo casi exclusivamente del lado vectorial, y el híbrido es híbrido solo de nombre.

**Fix propuesto** — dos opciones, no excluyentes: (a) declarar `analyzer="es.microsoft"` en `content`, `title` y `section_path` (stemming + folding, resuelve las dos mitades del problema); (b) mientras tanto, escribir los términos del glossary con la ortografía real. La opción (a) requiere reindexar; la (b) es un cambio de datos sin migración. **Antes de cualquier fix hay que verificar la hipótesis H-1 (abajo)**: si el índice fue creado a mano en el portal con un analizador español, la mitad de este hallazgo desaparece.

---

### IDX-03 · alta · No hay limpieza de chunks stale al reindexar

**Evidencia** — grep exhaustivo de los llamadores de `delete_analysis_chunks`:

```
./analysis/service.py:376        → delete_analysis(), solo si current_status == "error"
./analysis/cosmos_runtime.py:630 → delete_analysis_cosmos(), solo si current_status == "error"
```

Ni `extraction/runner.py::extract_and_index` (`:255-256`) ni `cosmos_runtime.py::extract_and_index_cosmos` (`:943-944`) lo llaman antes de `upload_chunks`.

Y `extraction/ai_search.py:177`:
```python
chunk_id = f"{analysis_id}--{chunk['document_id']}--{chunk['chunk_index']}"
```
con `client.upload_documents(...)` — que es un **upsert**, no un replace.

**Escenario de falla** — un análisis se reintenta desde estado `error` (`start_analysis_cosmos` lo permite explícitamente: `if analysis.get("status") not in {"draft", "error"}`). El primer run indexó 400 chunks; el segundo, tras un cambio de chunking o simplemente por variación de la extracción, genera 350. Los chunks 350-399 del primer run **siguen vivos** en el índice bajo el mismo `analysis_id`. El retrieval mezcla dos chunkings distintos del mismo documento, y el LLM recibe fragmentos que ya no corresponden al texto actual. Con el bug CHK-01 inflando el conteo de chunks, la varianza entre runs es alta.

**Fix propuesto** — llamar a `delete_analysis_chunks(analysis_id)` justo antes de `upload_chunks` en ambos runtimes. Alternativa sin ventana de inconsistencia: subir todos los chunks nuevos primero y después borrar por filtro `analysis_id eq X and chunk_index ge <nuevo_max>`.

---

### IDX-04 · media · El contrato de índice solo se valida en producción

**Evidencia** — `backend/extraction/ai_search.py:154-157`

```python
def upload_chunks(chunks_with_embeddings, analysis_id, correlation_id) -> None:
    settings = get_settings()
    if settings.is_production:
        validate_index_contract()
```

**Qué pasa** — fuera de `APP_ENV=production`, un drift de schema (campo faltante en el índice) solo produce el warning `search_index_document_fields_discarded` de `_to_index_document` (`:46-52`). El comentario de `_assert_index_contract` (`:102-108`) documenta que ese fue exactamente el incidente histórico con `primary_category`, y el fix protege producción pero deja el resto de los entornos igual que antes.

**Escenario de falla** — se valida el sistema en staging tras agregar un campo, el índice de staging no está migrado, el campo se descarta silenciosamente, y la degradación de retrieval se atribuye al modelo en vez de al schema.

**Fix propuesto** — validar siempre, con una variable de escape explícita (`SKIP_INDEX_CONTRACT_CHECK=true`) para los entornos donde se quiera saltear a propósito.

---

### IDX-05 · media · Bucle de borrado sin corte contra un índice de consistencia eventual

**Evidencia** — `backend/extraction/ai_search.py:79-90`

```python
while True:
    batch = [
        {"id": doc_id}
        for doc in client.search(search_text="*", top=500, select=["id"], filter=filter_expr)
        if (doc_id := doc.get("id"))
    ]
    if not batch:
        return
    client.delete_documents(documents=batch)
    sleep(0.1)
```

**Qué pasa** — Azure AI Search es de consistencia eventual: un documento borrado puede seguir apareciendo en búsquedas durante algunos segundos. `delete_documents` sobre un id ya borrado devuelve éxito, así que el bucle no tiene forma de distinguir "quedan documentos" de "el índice todavía no se actualizó". No hay contador de iteraciones ni timeout.

**Escenario de falla** — borrado duro de un análisis grande bajo carga: el bucle gira repitiendo el mismo lote hasta que el índice converge. No es infinito en la práctica, pero es un bucle sin cota superior dentro de un request HTTP.

**Fix propuesto** — cortar si el lote devuelto es idéntico al anterior, y agregar un máximo de iteraciones proporcional al conteo inicial.

---

# CAPA 4 — Retrieval

## Pipeline real, reconstruido del código

```
run_extractor (extractors/base.py:1036)
  ├─ keyword_query  = build_keyword_query(categoria)     → ~20-40 términos SIN acentos
  ├─ category_top_k = glossary.top_k | 25                → 25 o 35 según categoría
  └─ _retrieve_with_category_priority(top_k=category_top_k)      [base.py:910]
        ├─ over_fetch_k = top_k * 3                       → 75 o 105
        └─ search_hybrid(top_k=over_fetch_k, category_filter=None)  [azure_search.py:360]
              └─ _search_azure                                       [azure_search.py:253]
                    ├─ over_fetch    = max(top_k*3, 30)   → 225 o 315   ← 9× el top_k original
                    ├─ k_for_vector  = min(over_fetch,1000)
                    ├─ query_vector  = embed_query(query semántica)
                    ├─ bm25_text     = keyword_query
                    ├─ client.search(search_text=bm25_text, top=over_fetch,
                    │                vector_queries=[VectorizedQuery(...)],
                    │                filter="analysis_id eq '...'")
                    │                  → Azure fusiona BM25 + vectorial con RRF
                    ├─ sort por (@search.score, token_overlap)   ← no-op: Azure ya viene ordenado
                    ├─ _expand_children_to_parents(ranked[:top_k*2])
                    │     → 1 llamada HTTP get_document() POR CADA chunk child
                    └─ return expanded[:top_k]              → 75 o 105
        ├─ boost ×1.20 a los chunks cuya categoría coincide
        ├─ sort desc
        └─ return [:top_k]                                 → 25 o 35
  ├─ _truncate_to_token_budget(16000 tokens)
  ├─ _format_chunks → prompt
  └─ _call_llm
```

**No hay reranker.** Ni semántico de Azure (`query_type="semantic"` / `SemanticConfiguration`), ni cross-encoder propio, ni nada. El grep por `rerank|semantic|query_type|ScoringProfile` en todo el repo no devuelve una sola línea de configuración. El único "reranking" del pipeline es (a) el re-sort por el score que Azure ya calculó, que es un no-op, y (b) el boost multiplicativo de +20% por categoría.

Respondiendo puntualmente tus preguntas de esta capa:

- *¿Se descartan documentos por un threshold mal calibrado?* — **No hay ningún threshold de score en el retrieval.** El corte es puramente por `top_k` y después por presupuesto de tokens. Esto es mejor que un threshold mal calibrado, pero significa que siempre entran 25-35 chunks al prompt aunque los últimos sean irrelevantes (ver RET-04).
- *¿El threshold se aplica antes de terminar de recuperar?* — no aplica, no hay threshold.
- *¿Se hace reranking?* — no, ver arriba.
- *¿El contexto contiene la evidencia o el pipeline "cree" que la tiene?* — ver RET-04 y la Capa 5.

---

### RET-01 · crítica · `_expand_children_to_parents` duplica el parent cuando parent y child matchean juntos

**Evidencia** — `backend/shared/ports/azure_search.py:211-228`

```python
for chunk in chunks:
    chunk_type = chunk.get("chunk_type")

    if chunk_type == "parent":
        chunk_id = chunk.get("id")
        if chunk_id:
            seen_parent_ids.add(chunk_id)
        expanded.append(chunk)          # ← append INCONDICIONAL: no chequea seen_parent_ids
        continue

    if chunk_type != "child" or not chunk.get("parent_chunk_id"):
        expanded.append(chunk)
        continue

    parent_id = chunk["parent_chunk_id"]
    if parent_id in seen_parent_ids:
        continue                        # ← este SÍ deduplica
```

**Qué debería pasar** — el docstring lo dice explícitamente: *"Si un chunk 'parent' ya vino matcheado directamente, también se registra para que un child del mismo parent no lo duplique."*

**Qué pasa** — la dedupe es asimétrica. Funciona en el orden `parent → child`, pero **no** en el orden `child → parent`: si el child aparece primero (mejor score), se expande a su parent y se agrega `parent_id` a `seen_parent_ids`; cuando después llega el parent original en la lista, la rama de la línea 214 lo appendea sin consultar el set.

**Por qué el orden `child → parent` es el caso frecuente, no el raro** — el texto del parent **contiene** el del child por construcción (`chunking.py:1329-1338`). Los dos matchean la misma query. El child, al ser más corto, tiene mayor densidad de términos y BM25 lo favorece (normalización por longitud). Así que el child arriba y el parent abajo es el orden esperable.

**Escenario de falla** — el artículo 14 con incisos aparece dos veces, idéntico, en los 25 chunks del contexto. Consume dos slots de top_k (desplazando dos chunks relevantes fuera del contexto), y el LLM lee el mismo texto dos veces. Como el prompt del sistema premia con **+0.2 de confidence** el "dato consistente en múltiples fragmentos" (`_base_system.txt:86`), el sistema se autovalida con una copia de sí mismo. Además el extractor puede emitir dos ítems del mismo hecho, que `merge_node` dedupe solo si el `valor` normalizado coincide exactamente.

**Fix propuesto** — una línea: en la rama `chunk_type == "parent"`, `if chunk_id in seen_parent_ids: continue` antes del append.

---

### RET-02 · alta · El filtro por categoría es código muerto

**Evidencia** — todos los llamadores de `search_hybrid` fuera de tests:

```
./analysis/extraction/extractors/base.py:953    category_filter=None,  # ← CLAVE: Sin filtro
./analysis/extraction/graph.py:1015             category_filter=None,
./analysis/extraction/synthesis.py:626          category_filter=None,
```

**Qué pasa** — todo el bloque de `_search_azure:302-332` (construcción del filtro OData, el fallback wildcard condicionado, el log `azure_search_no_results_with_category` con su comentario sobre por qué devolver vacío es "más seguro que wildcard") nunca se ejecuta. Es lógica cuidadosamente razonada, comentada y muerta.

**Por qué importa más allá de la limpieza** — el fallback wildcard (`:317-324`) **sí** está vivo, porque solo se saltea cuando hay `category_filter`. Como nunca lo hay, la condición `if not raw_results and not category_filter` es siempre `if not raw_results`. Es decir: **el pipeline siempre hace fallback a wildcard cuando la búsqueda no devuelve nada** — justamente el comportamiento que el comentario declara peligroso ("retornar chunks aleatorios que el LLM podría usar para 'extraer' información incorrecta"). La protección que el comentario describe no existe en ningún camino real.

**Escenario de falla** — categoría `causales_rechazo` en un pliego que no tiene una sección de causales. BM25 con los términos sin acentos (IDX-02) no matchea nada, el vector tampoco pasa el filtro de `analysis_id`… si la búsqueda vuelve vacía, se dispara `_run_query(analysis_filter, "*", top=225)` y entran 25 chunks arbitrarios al prompt de causales de rechazo. El LLM tiene instrucciones fuertes de no inventar, pero está recibiendo contexto explícitamente irrelevante para una categoría marcada en el prompt como *"la categoría más crítica"*.

**Fix propuesto** — decidir la arquitectura: o se borra el parámetro `category_filter` y el fallback wildcard queda gobernado por su propia condición explícita, o se reactiva el filtro. En cualquier caso, el fallback wildcard debería estar detrás de un flag y loguearse como error, no como warning.

---

### RET-03 · alta · Amplificación de `top_k` y expansión children→parent con una llamada HTTP por child

**Evidencia** — dos multiplicaciones encadenadas:

`extractors/base.py:946`
```python
over_fetch_k = top_k * 3
all_candidates = search_hybrid(top_k=over_fetch_k, ...)
```

`shared/ports/azure_search.py:270` y `:354-355`
```python
over_fetch = max(top_k * 3, 30)
...
expansion_window = ranked_chunks[: max(top_k * 2, top_k)]
expanded_chunks = _expand_children_to_parents(client, expansion_window)
```

y dentro de `_expand_children_to_parents:231`
```python
parent_document = client.get_document(key=parent_id)   # ← HTTP síncrono, uno por child
```

**Números reales** — para `garantias` (`top_k=35` en el glossary): `over_fetch_k=105` → `over_fetch = 315` documentos pedidos a Azure → `expansion_window = ranked[:210]` → hasta **210 llamadas `get_document()` secuenciales**, solo para esa categoría. Por 8 categorías en paralelo (el grafo las corre con `add_edge("setup", node)` para los 8), eso es hasta ~1500 round-trips HTTP sincrónicos por análisis, en el camino más caliente.

**Escenario de falla** — un pliego largo con muchos artículos con incisos (o sea: cualquier pliego bien estructurado, que es donde el parent/child aporta) hace que la etapa de extracción tarde varios minutos más de lo esperado. Como `calculate_timeout_minutes` dimensiona el timeout por cantidad de páginas y no por cantidad de chunks child, el análisis puede vencer por timeout en documentos estructurados y no vencer en documentos planos del mismo largo.

**Fix propuesto** — recolectar los `parent_chunk_id` únicos de la ventana y resolverlos en **una** búsqueda con filtro `search.in(id, '...')` en vez de N `get_document()`. Y reducir la amplificación: `over_fetch` ya se aplica dos veces (`base.py` y `azure_search.py`) — una de las dos sobra.

---

### RET-04 · media · El presupuesto de tokens no cuenta lo que realmente entra al prompt

**Evidencia** — `extractors/base.py:402-408`

```python
for index, chunk in enumerate(chunks):
    cost = _count_tokens(str(chunk.get("content", "")))    # ← SOLO content
    if used + cost > budget and kept:
```

contra `extractors/base.py:119-127`, que es lo que efectivamente se manda:

```python
header = (
    f"[Fragmento: F{position}, "
    f"Documento: {chunk.get('document_id', 'desconocido')}, "     # UUID completo
    f"Página: {chunk.get('page_number', 0)}, "
    f"Sección: {chunk.get('section_path', 'general')}, "          # ruta completa de headings
    f"Tipo: {'TABLA' if ... else 'PÁRRAFO'}"
    f"{_table_hint(chunk)}]"
)
formatted.append(f"{header}\n{chunk.get('content', '')}")
```

**Qué pasa** — el presupuesto de 16000 tokens mide solo el cuerpo de los chunks. No cuenta: los headers (un UUID ≈ 20 tokens + `section_path` que puede ser largo, ~40-60 tokens por chunk × 35 chunks ≈ 1500-2000 tokens), ni el system prompt (`_base_system.txt` son 6.5 KB), ni el prompt de categoría (`garantias.txt` son 13 KB). El contexto real es del orden de 21000-23000 tokens cuando el código cree que son 16000.

**Escenario de falla** — no rompe hoy (gpt-4o tiene 128k), pero el mecanismo de control de costo/contexto no controla lo que dice controlar. Si mañana se baja el presupuesto para reducir costo, la reducción real será menor a la esperada y el warning `extraction_chunks_dropped_token_budget` seguirá reportando un número que no corresponde al prompt.

**Fix propuesto** — medir el costo sobre `header + content`, y descontar del presupuesto el tamaño fijo de system + category prompt (calculable una vez por categoría con `_count_tokens`).

---

### RET-05 · media · El fallback sin `response_format` enmascara errores transitorios

**Evidencia** — `extractors/base.py:174-178`

```python
try:
    bound = llm.bind(response_format={"type": "json_object"})
    response = bound.invoke(messages)
except Exception:  # noqa: BLE001
    response = llm.invoke(messages)
```

**Qué debería pasar** — el fallback existe para el caso "este deployment no soporta JSON mode", que es un error de capacidad determinista.

**Qué pasa** — el `except Exception` captura **todo**: rate limit (429), timeout, error de red, content filter. En cualquiera de esos casos se reintenta inmediatamente **sin JSON mode**, duplicando el costo del request fallido y aumentando la chance de una respuesta no parseable. Recién después actúa el `@retry` de tenacity, que a su vez reintenta ambos.

**Escenario de falla** — bajo rate limit (habitual con 8 categorías en paralelo contra el mismo deployment), cada categoría hace hasta 6 llamadas (3 intentos × 2 modos) en vez de 3, agravando el propio rate limit.

**Fix propuesto** — capturar solo el error específico de capacidad (típicamente `BadRequestError` con código `unsupported_parameter` / mensaje sobre `response_format`), o detectar el soporte una vez al arrancar y cachearlo.

---

# CAPA 5 — Construcción del contexto

### CTX-01 · alta · El heading no llega al prompt como texto, solo como metadata de header

**Evidencia** — `extractors/base.py:119-127` (ver RET-04). El heading aparece como `Sección: <section_path>` dentro del header del fragmento, y el system prompt (`_base_system.txt`) instruye explícitamente:

> `Sección` | Ruta de encabezados del pliego hasta ese punto | **Es contexto, NO filtro.** Leé el texto aunque el título no mencione la categoría.

**Qué pasa** — esto está bien resuelto para el LLM: la ruta de headings sí llega. El problema es el escalón anterior: por IDX-01 el chunk **nunca se recupera** si el único indicio de su relevancia estaba en el heading. La relación título→párrafo se preserva en el prompt pero se pierde en el retrieval.

**Escenario de falla** — el mismo de IDX-01. No es un hallazgo independiente sino la confirmación de que el problema es de indexación y no de construcción de contexto: si el chunk llega, el heading llega bien.

**Fix propuesto** — ver IDX-01. No hay nada que corregir en `_format_chunks`.

---

### CTX-02 · media · Los 25-35 chunks entran completos, sin corte por relevancia

**Evidencia** — `extractors/base.py:1066-1080`: se recuperan `category_top_k` chunks y se truncan solo por presupuesto de tokens. No hay ningún corte por score.

**Qué pasa** — el chunk en la posición 35 tiene un score de RRF típicamente ~2× menor que el primero, pero entra al prompt con el mismo peso visual que el primero. Y el orden en que entran es el orden de relevancia (correcto: lo más relevante primero, que es lo que favorece la atención del modelo).

**Escenario de falla** — categorías que en un pliego dado tienen poca evidencia real (ej. `criterios_evaluacion` en un pliego que adjudica por menor precio sin matriz). Los 25 chunks se llenan con secciones tangenciales boosteadas, y el LLM —al que se le pidió ser "analista experto que reconoce el concepto aunque el vocabulario cambie"— tiene mucho material del cual construir un criterio que el pliego no tiene. La instrucción de no inventar está, pero la presión del contexto va en contra.

**Fix propuesto** — corte relativo: descartar los chunks cuyo score sea menor a una fracción del score máximo de esa consulta (ej. `score < 0.5 * max_score`). Es más robusto que un threshold absoluto porque los scores de RRF no son comparables entre queries.

---

### CTX-03 · media · Categorías declaradas en el contrato que ningún extractor completa

**Evidencia** — `analysis/extraction/graph.py:914-935` (dentro de `merge_node`)

```python
"documentos_requeridos": [],
"documentos_extraction_status": "not_found",
...
"restricciones_participacion": [],
"restricciones_extraction_status": "not_found",
"cronograma_proceso": [],
"cronograma_extraction_status": "not_found",
"estimacion_presupuesto": None,
"presupuesto_extraction_status": "not_found",
```

**Qué pasa** — cuatro campos del contrato `ExtractedData` están hardcodeados a vacío con status `not_found`. No hay ningún nodo del grafo que los complete (los 8 nodos extractores están listados en `graph.py:1136-1145` y ninguno mapea a estos campos).

**Escenario de falla** — el frontend distingue `not_found` ("el pliego no lo dice") de otros estados. Para estos cuatro campos el usuario lee **"no encontrado"** cuando la verdad es **"no analizado"**. Para `estimacion_presupuesto` en particular eso es grave: un oferente puede concluir que el pliego no publica presupuesto oficial cuando en realidad el sistema nunca lo buscó por esa vía (solo lo captura el regex de rescate de `identificacion_procedimiento`).

**Fix propuesto** — usar un status distinto (`not_analyzed` / `not_implemented`) y que el frontend lo renderice como "fuera de alcance de este análisis", o eliminar los campos del contrato.

---

### CTX-04 · media · Los conflictos detectados nunca llegan al usuario a través de la narrativa

**Evidencia** — `graph.py:940-985` detecta conflictos (fechas distintas para el mismo tipo de plazo, montos distintos para el mismo tipo de garantía) y los guarda en `state["conflicts"]`. Pero `synthesize_node` (`:1054-1120`) llama a `run_synthesis(category_key=..., items=items, ...)` **sin pasar los conflictos**, y `run_synthesis` (`synthesis.py:537-600`) construye el prompt solo con `{items_json}`.

Además, en los prompts de extracción el único tratamiento de contradicciones es una línea de la tabla de confidence (`_base_system.txt:88`: `| Valores contradictorios entre fragmentos | -0.2 |`). No hay ninguna instrucción sobre **cómo** resolverlas (ej. preferir el Pliego de Condiciones Particulares sobre el General, o reportar ambas).

**Escenario de falla** — un pliego cuyo cuerpo dice "garantía de mantenimiento: 1%" y cuyo Anexo de la circular modificatoria dice "5%". Ambos ítems sobreviven a la dedupe (montos distintos), `merge_node` registra el conflicto correctamente, y la narrativa que lee el usuario dice las dos cosas en dos bullets seguidos sin ninguna marca de que se contradicen. El conflicto queda en un campo del estado que la síntesis nunca ve.

**Fix propuesto** — pasar `conflicts` filtrados por categoría a `run_synthesis` e incorporar al `_response_base.txt` una regla explícita: si un ítem está en conflicto, el bullet debe declararlo ("El pliego indica 1% en el cuerpo y 5% en la Circular Nº 2 — verificar").

---

# CAPA 6 — LLM / síntesis

### SYN-01 · crítica · El LLM de síntesis nunca ve los chunks, pero se le pide evidencia textual del pliego

**Evidencia** — `synthesis.py:563-570`

```python
prompt = (
    _load_response_base_prompt()
    .replace("{items_json}", _serialize_items(items))
    .replace("{category_label}", category_label)
    .replace("{category_output_contract}", category_contract)
)
raw, token_usage = extractors_base._call_llm(messages=[("human", prompt)], correlation_id=correlation_id)
```

`_load_response_base_prompt` concatena `_response_base.txt` + `_output_schema.txt`. Ninguno de los dos tiene un placeholder de chunks — lo verifiqué: `grep -c "{chunks}" _response_base.txt _output_schema.txt` → `0` en ambos.

Y sin embargo `_output_schema.txt:90-106` pide:

> **Campo `evidence` (CRÍTICO para highlighting preciso)**
> **Propósito:** Identificar las FRASES EXACTAS del pliego que sustentan tu respuesta.
> 1. **Text debe ser LITERAL** — Copiá el texto exacto de `citation` en `source_references`. NO parafrasees, NO resumas, NO reordenes palabras.

**Qué pasa** — el único texto del pliego que el modelo de síntesis tiene es el campo `citation` dentro de los `source_references` de cada ítem. Se le pide que lo transcriba palabra por palabra a `evidence.text`. Es una tarea de copia exacta de cadenas de hasta 300 caracteres, delegada a un LLM generativo, cuyo resultado se valida después por substring exacto.

**Por qué es crítico** — porque de esa transcripción depende que la categoría entera se muestre o no (ver SYN-02).

**Fix propuesto** — no pedirle al LLM que transcriba. `raw.evidence` debería llevar solo `item_ref` + `claim`, y el `text` debe tomarse programáticamente de `items[item_ref].source_references[].citation`, que ya está verificado contra los chunks en la etapa de extracción. Eso elimina toda la clase de fallas de transcripción de un plumazo.

---

### SYN-02 · crítica · Si las evidencias no resuelven, la categoría se muestra como "no encontrada" aunque los datos existan

**Evidencia** — `synthesis.py:362-370`

```python
# NUEVO: Si hay evidencias NO VACÍAS, construir sources desde ahí
if raw.evidence and len(raw.evidence) > 0 and chunks_by_id:
    logger.info("using_evidence_based_resolution", ...)
    return _resolve_from_evidence(raw, chunks_by_id, correlation_id=correlation_id)   # ← return incondicional

# Flujo estándar: usar item_refs (backward compatible)
```

`_resolve_from_evidence` descarta cada evidencia que no encuentra (`:122-152`), y descarta cada bloque que se queda sin `source_ids` (`:212-218`, `:229-230`, `:242-243`). Si se descartan todas:

`synthesis.py:582-583`
```python
if not narrative.blocks:
    narrative = _empty_category_narrative(category_label)
```

`synthesis.py:493-510`
```python
"text": f"No se encontró información sobre {category_label} en los documentos del pliego.",
```

**Qué debería pasar** — si la resolución por evidencias falla, caer al camino `item_refs`, que resuelve contra los `source_references` propios de cada ítem (ya verificados por `_verify_citation_grounding` en la extracción) y no depende de ninguna transcripción del LLM.

**Qué pasa** — no hay fallback. El `return` de la línea 370 es incondicional. Ocho ítems de garantías extraídos, verificados contra los chunks y con citas válidas se convierten en **"No se encontró información sobre Garantías en los documentos del pliego."**

**Los cuatro disparadores, todos plausibles:**

1. El LLM parafrasea mínimamente la cita al copiarla (cambia una coma, corrige una tilde, colapsa un espacio). El matching de `:139` es `evidence_normalized in chunk_content_normalized` — tolera acentos y espacios, pero no una palabra distinta.
2. El LLM no copia exacto el UUID del `document_id` (`:119`, comparación de igualdad estricta contra `c.get("document_id")`).
3. El chunk que contiene la cita **no está** en `chunks_by_id`, porque ese índice es un muestreo de a lo sumo 1000 chunks (ver SYN-03).
4. El chunk que contenía la cita era un `child` y `_build_chunks_by_id_index` lo reemplazó por su `parent` (por RET-01/`_expand_children_to_parents`): si la cita estaba en el inciso pero el `content` del parent la contiene, matchea; si la cita venía del child expandido con `matched_child_content`, ese campo se pierde al reconstruir el índice.

**Cobertura parcial también es fatal** — no hace falta que fallen *todas* las evidencias. `get_source_ids_for_item_refs` (`:177-205`) devuelve `[]` para cualquier ítem que no tenga una evidencia resuelta, y ese bullet/párrafo/fila se descarta (`paragraph_dropped_no_evidence`). Si el LLM emite evidencias para 3 de 10 ítems, el usuario ve 3 bullets y los otros 7 desaparecen sin ninguna señal.

**Fix propuesto** — el fix de mayor impacto/menor esfuerzo de toda esta auditoría:

```python
if raw.evidence and chunks_by_id:
    narrative = _resolve_from_evidence(raw, chunks_by_id, correlation_id=correlation_id)
    if narrative.blocks:
        return narrative
    logger.warning("evidence_resolution_empty_falling_back_to_item_refs", ...)
# cae al camino item_refs
```

Y un log de nivel `error` cuando la cobertura de evidencias sea < 100% de los ítems referenciados, porque hoy eso es invisible.

---

### SYN-03 · crítica · `search_hybrid(query="*", top_k=1000)` se ejecuta 8 veces por análisis y no devuelve "todos los chunks"

**Evidencia** — dos funciones distintas hacen la misma consulta:

`graph.py:1010-1016` (una vez por análisis, en `synthesize_node`)
```python
all_chunks = search_hybrid(
    query="*",  # Wildcard = obtener todos los chunks
    analysis_id=analysis_id,
    top_k=1000,  # Límite máximo de Azure Search
    keyword_query=None,
    category_filter=None,
)
```

`synthesis.py:621-627` (dentro de `enrich_narrative_with_highlights`, sin caché)
```python
all_chunks = search_hybrid(query="*", analysis_id=analysis_id, top_k=1000, ...)
```

Y `graph.py:1088-1109` la llama **una vez por categoría**:
```python
for category_key in NARRATIVE_CATEGORIES:          # 7 categorías
    ...
    if document_mapping:
        narrative = enrich_narrative_with_highlights(..., analysis_id=state["analysis_id"])
        #            └─ dentro: _build_chunks_index_from_search(analysis_id, ...)
```

**Tres problemas verificados en una sola línea de código:**

1. **Se ejecuta 8 veces** (1 en `_build_chunks_by_id_index` + 7 en el loop de categorías). Cada ejecución dispara: una llamada de embedding a Azure OpenAI, una búsqueda con `top=3000` (`over_fetch = max(1000*3, 30)`), y `_expand_children_to_parents` sobre una ventana de 2000 candidatos con **una llamada `get_document()` por cada child**. Sin ninguna caché entre las 8.

2. **Embebe el literal `"*"`.** `_embed_query_or_none("*")` genera un embedding real del carácter asterisco y hace una búsqueda vectorial con `k_nearest_neighbors=1000` contra él. Los resultados son los 1000 chunks más cercanos al embedding de `"*"` — un subconjunto arbitrario pero **sesgado**, no una muestra uniforme.

3. **El comentario es falso.** `# Wildcard = obtener todos los chunks` no describe lo que pasa. Con RRF fusionando BM25(`*`) y vectorial(embed(`*`)), y con tope de 1000, para un análisis con más de 1000 chunks se obtiene un muestreo sesgado. Y por CHK-01 el conteo de chunks está inflado ~40-67%, así que ese tope se alcanza antes de lo esperable.

**Escenario de falla** — un pliego de 150 páginas genera >1000 chunks. El índice `chunks_by_id` cubre solo una fracción sesgada. La cita de una garantía que quedó fuera del muestreo no resuelve → SYN-02 → **"No se encontró información sobre Garantías"** en un pliego que sí las exige. Y todo esto después de haber pagado 8 embeddings + 8 búsquedas de 3000 + cientos de `get_document()`.

**Fix propuesto** — tres cosas, en orden: (a) no usar `search_hybrid` para enumerar; usar `client.search(search_text="*", filter=..., select=[...])` sin vector y paginando por `$skip`/continuation hasta agotar; (b) construir el índice **una sola vez** en `synthesize_node` y pasarlo a `enrich_narrative_with_highlights` como parámetro (la firma ya acepta `chunks_by_doc_page`); (c) loguear a nivel `error` si el conteo devuelto llega al tope.

---

### SYN-04 · alta · Los dos caminos de resolución de sources tienen garantías distintas, y el docstring describe solo uno

**Evidencia** — `synthesis.py:347-360`, docstring de `_resolve_narrative_sources`:

> *"Esto es lo que hace estructuralmente imposible que la fuente de un bloque sea la evidencia de un item distinto: `sources` solo se puede poblar desde `item_stubs[i]` para los indices `i` que el LLM efectivamente referencio, nunca desde un pool global de la categoria."*

Esa garantía la implementa el camino `item_refs` (`:380-418`), donde cada source sale literalmente de `_item_source_stubs(items[i])` — una copia de las citas ya verificadas del ítem apuntado.

En el camino evidence (`_resolve_from_evidence:163-171`) la source se construye así:

```python
source = {
    "id": len(all_sources),
    "document_id": chunk["document_id"],
    "page_number": chunk["page_number"],
    "citation": ev.text,          # ← texto que produjo el LLM de síntesis
    "unverified": False,          # ← se marca como verificado por construcción
    "highlight_regions": [],
    "chunk_id": chunk_id,
}
```

**Qué pasa** — `citation` es texto emitido por el LLM (validado solo por `min_length=12` en `RawEvidence.text` y por estar contenido en algún chunk de esa página), y su vinculación con un ítem concreto viene de `ev.item_refs`, que también lo decide el LLM. Nada obliga a que `ev.text` sea una de las citas verificadas de ese ítem.

**Escenario de falla** — el LLM redacta un bullet sobre la garantía de cumplimiento de contrato (ítem 3) y le adjunta como evidencia una frase que copió de la cita del ítem 1 (garantía de mantenimiento de oferta), porque ambas están en la misma página. La frase existe en un chunk de esa página, así que resuelve sin error. El usuario ve un bullet sobre garantía de cumplimiento cuya fuente, al hacer clic, muestra el texto de la garantía de oferta. **Esto es exactamente la falla que el docstring afirma que es estructuralmente imposible** — y lo era, hasta que se agregó el camino evidence encima sin extender la garantía.

Nota adicional: el camino evidence tampoco pasa por `_dedupe_narrative_sources`, así que las banderas `unverified` y `block_id` se manejan distinto en cada rama.

**Fix propuesto** — el mismo que SYN-01: que `evidence` no lleve texto libre, sino `item_ref` + offset dentro de la cita ya verificada de ese ítem. Eso restaura la garantía estructural en ambos caminos.

---

### SYN-05 · media · La confianza que ve el usuario es autoevaluación del LLM, no una medición

**Evidencia** — dos sistemas de confidence que compiten:

`graph.py:598-608`
```python
def _normalize_confidence(item: dict) -> dict:
    status = str(item.get("extraction_status", "success"))
    refs = list(item.get("source_references", []))
    if "confidence" not in item:
        item["confidence"] = calculate_confidence(refs, status)   # ← determinista, casi nunca se usa
    else:
        conf = float(item.get("confidence", 0.0) or 0.0)
        item["confidence"] = max(0.0, min(conf, 1.0))             # ← se respeta lo que dijo el LLM
    item["confidence_level"] = get_confidence_level(...)
```

Y `_base_system.txt:80-92` le pide al LLM que calcule su propia confidence con una tabla de ajustes.

**Qué pasa** — como el prompt pide explícitamente el campo `confidence`, el LLM casi siempre lo emite, y por lo tanto `calculate_confidence` (la fórmula determinista basada en cantidad de fuentes y longitud de cita) prácticamente nunca corre. Lo que el usuario ve como "confianza alta / media / baja" es la autoevaluación del modelo.

**El círculo vicioso** — ambas fórmulas premian la longitud de la cita:
- LLM: `| Cita supera 100 caracteres de contexto | +0.1 |` (`_base_system.txt:87`)
- Código: `if avg_citation_length > 100: confidence += 0.2` (`graph.py:581-584`)

Y el pipeline **ensancha las citas por su cuenta**: `_expand_short_paragraph_citation` (`base.py:462-488`), `_widen_citation_with_chunk_context` (`base.py:491-521`) y `_rescue_paragraph_citation` (`base.py:543-552`) reescriben la cita hasta llegar a `CITATION_PREFERRED_MIN_CHARS = 40`. O sea: el sistema alarga la cita y después se premia a sí mismo por tenerla larga.

**Escenario de falla** — `get_confidence_level` marca "alta" a partir de 0.8, y el prompt define 0.80–1.00 como *"usable sin abrir el PDF"*. Un ítem cuya evidencia real era una frase de 20 caracteres, ensanchada por el código a 40+, puede presentarse al usuario como usable sin verificar.

**Fix propuesto** — usar siempre `calculate_confidence` (determinista, auditable) y guardar la confidence del LLM en un campo aparte para telemetría. Y sacar la longitud de cita como factor: no mide calidad de evidencia, y hoy mide una decisión del propio pipeline.

---

### SYN-06 · media · El umbral mínimo de cita (12 caracteres) no es discriminante

**Evidencia** — `schemas.py:36`
```python
CITATION_MIN_CHARS = 12
```

usado como único piso de validez en `base.py:605-622`:
```python
# La longitud NO es el criterio de validez: lo es que el texto exista
# literalmente en un chunk recuperado (ver `CITATION_MIN_CHARS`). El único
# piso que queda descarta citas demasiado cortas para ser discriminantes
# ("oferta", "garantía"), que harían match en cualquier chunk.
if len(citation_text) < CITATION_MIN_CHARS:
    return False
```

**Qué pasa** — el comentario da como ejemplos de cita no discriminante `"oferta"` (6) y `"garantía"` (8). Pero `"las garantías"` son 13 caracteres y pasa. `"del contrato"` son 12 y pasa. `"la presente"` son 11 y no pasa por un carácter.

El chequeo de grounding es `normalized_citation in normalized_content` sobre chunks de 700 tokens. Una cadena de 12-15 caracteres genérica matchea en prácticamente cualquier chunk de la categoría.

**Escenario de falla** — el LLM alucina un dato ("garantía de impugnación del 3%") y emite como cita `"las garantías"`, que existe literalmente en el chunk. `_verify_reference_grounded` devuelve `True`, `any_verified = True`, el ítem conserva status `success`. La verificación anti-alucinación pasa sobre una cita que no contiene el dato.

Mitigación parcial que sí existe: `_penalize_unverifiable` y las funciones de ensanchado intentan llevar la cita a 40 caracteres. Pero si el ensanchado no encuentra ancla (`_expand_short_paragraph_citation:486-488`, "Política estricta: no expandir por match de palabra suelta"), la cita corta sobrevive tal cual.

**Fix propuesto** — subir el piso de *validez* a `CITATION_PREFERRED_MIN_CHARS` (40) y, más importante, verificar que la cita contenga el **valor** del ítem (el número, el monto, la fecha) y no solo que exista en el chunk. Ese es el chequeo que realmente detecta alucinación.

---

### SYN-07 · baja · Los prompts no piden síntesis entre chunks explícitamente

**Evidencia** — la única instrucción sobre información distribuida está en `_base_system.txt:63` (tabla de campos):

> | Orden | Por relevancia semántica, no por documento | Un dato puede estar partido en dos fragmentos. **Consolidalo si es coherente.** |

y `:70`: *"Si el mismo hecho aparece en múltiples fragmentos: consolidalo y sumá las citas."*

**Qué pasa** — ambas hablan de consolidar **el mismo hecho** repetido, no de **componer un hecho** a partir de piezas que están en fragmentos distintos. Preguntaste puntualmente por esto: no hay instrucción de sintetizar entre chunks.

**Escenario de falla** — el fragmento F3 dice *"la garantía de mantenimiento de oferta será del 1% del presupuesto oficial"* y el F11 (otra sección) dice *"el presupuesto oficial asciende a $ 45.000.000"*. El monto absoluto de la garantía requiere componer los dos. El prompt no lo pide y la regla 1 (*"No infieras, no deduzcas por contexto, no completes por analogía"*) más bien lo desalienta. Es una decisión defendible desde el anti-alucinación, pero conviene que sea explícita en vez de emergente.

**Fix propuesto** — agregar una regla que autorice la composición **con doble cita obligatoria**: si un dato surge de combinar dos fragmentos, el ítem debe llevar los dos `source_references` y status `partial`. Eso mantiene el grounding y habilita el caso.

---

# CAPA 7 — Source attribution

## Los cuatro conceptos, y dónde se conectan y desconectan

| Concepto | Dónde vive en el código | Estado |
|---|---|---|
| **retrieved chunk** | `_retrieve_with_category_priority` → lista `chunks` en `run_extractor` (`base.py:1066`) | Existe como entidad. Nunca se persiste su identidad. |
| **used evidence** | `item["source_references"][].citation` tras `_verify_citation_grounding` (`base.py:803`) | Se verifica contra `(document_id, page_number)`, **nunca contra un chunk_id**. |
| **displayed source** | `narrative.sources[]` construido en `_resolve_narrative_sources` (`synthesis.py:340`) | Reconstruido de cero por un segundo LLM, por dos caminos con garantías distintas. |
| **highlight** | `source.highlight_regions` de `compute_highlights_for_sources` (`highlight.py:379`) | Recalculado a mano sobre el PDF, ignorando toda la cadena anterior. |

### ATR-01 · crítica · La identidad del chunk se pierde en la extracción y nunca se recupera

**Evidencia** — `extractors/base.py:816-819`

```python
chunks_by_doc_page: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
for chunk in chunks:
    key = (str(chunk.get("document_id", "")), int(chunk.get("page_number", 0) or 0))
    chunks_by_doc_page[key].append(chunk)
```

y `:834-836`
```python
citation = str(ref.get("citation", ""))
key = (str(ref.get("document_id", "")), int(ref.get("page_number", 0) or 0))
candidates = chunks_by_doc_page.get(key)
```

**Qué pasa** — una cita se considera *grounded* si aparece en **cualquier** chunk de ese documento+página. El código sabe cuál de los candidatos matcheó (`_citation_verified_in_paragraph_chunk` itera sobre ellos en el `any()` de la línea 622), pero **descarta esa información**: no escribe `chunk_id` en el `ref`.

Y el `id` del chunk sí está disponible: `_document_to_chunk` lo pone en `chunk["id"]` (`azure_search.py:150`). Está a una línea de distancia.

**Consecuencia en cadena** — porque no se guarda, todo lo que sigue tiene que reconstruirlo por texto:
- `synthesis.py::_resolve_from_evidence` lo reconstruye buscando la cita en `chunks_by_id` (y por eso necesita SYN-03, que es donde se rompe).
- `highlight.py::compute_highlights_for_sources` lo reconstruye buscando la cita en `chunks_by_doc_page`.

Dos reconstrucciones frágiles y costosas de un dato que se tenía gratis.

**Escenario de falla** — una página con dos chunks: el del artículo 9 (adjudicación) y el del artículo 10 (garantías), ambos con la frase *"conforme lo establecido en el presente pliego"*. El LLM cita esa frase para un dato de garantías. `_verify_citation_grounding` la valida contra el chunk del artículo 9 (el primero de la lista) y no registra nada. Después, el highlight la busca de nuevo y puede resolverla al artículo 9. El usuario hace clic en un dato de garantías y aterriza en adjudicación.

**Fix propuesto** — en `_verify_citation_grounding`, cambiar el `any(...)` por un loop que capture el chunk que matcheó y escriba `normalized_ref["chunk_id"] = chunk["id"]`. Propagarlo por `_item_source_stubs` → `narrative.sources` → `compute_highlights_for_sources`. Es el cambio de mayor apalancamiento de toda la capa de attribution: convierte tres búsquedas por texto en tres lookups por clave.

---

### ATR-02 · alta · La cita que se muestra no es la que el modelo usó: el pipeline la reescribe

**Evidencia** — `extractors/base.py:846-871`

```python
if _verify_reference_grounded(citation_for_verification, candidates):
    any_verified = True
    normalized_ref = dict(ref)
    final_citation = citation_for_verification
    if not _is_table_citation(citation):
        ...
        final_citation = _expand_short_paragraph_citation(citation_for_verification, candidates, preferred_snippet=...)
        if len(final_citation) < CITATION_PREFERRED_MIN_CHARS:
            richer = _rescue_paragraph_citation(item, candidates, category=category)
            if richer and len(richer) > len(final_citation):
                final_citation = richer
        if len(final_citation) < CITATION_PREFERRED_MIN_CHARS:
            final_citation = _widen_citation_with_chunk_context(final_citation, candidates)
    normalized_ref["citation"] = clip_citation(final_citation)
```

y el caso más fuerte, `:875-882`:
```python
if not _is_table_citation(citation):
    rescued_citation = _rescue_paragraph_citation(item, candidates, category=category)

if rescued_citation:
    any_verified = True                          # ← el ítem pasa a verificado...
    normalized_ref = dict(ref)
    normalized_ref["citation"] = rescued_citation  # ← ...con una cita que el LLM nunca emitió
    verified_refs.append(normalized_ref)
```

**Qué pasa** — tres transformaciones distintas reescriben la cita después de la verificación:

1. **Ensanchado** (`_widen_citation_with_chunk_context`): toma la cita verificada y le agrega ~100 caracteres a la izquierda y ~140 a la derecha del chunk (`_build_context_citation:675-678`). El texto resultante sigue siendo literal del pliego, pero **no es lo que el modelo citó**.
2. **Sustitución por otro campo** (`_expand_short_paragraph_citation` con `preferred_snippet`): reemplaza la cita por `item["texto_original"]` si ese texto está grounded.
3. **Rescate** (`_rescue_paragraph_citation`): cuando la cita del LLM **no** se puede verificar, busca si `item["valor"]` o `item["texto_original"]` están grounded y, si lo están, **los usa como cita** y marca el ítem como verificado.

El caso 3 es el más delicado: la verificación anti-alucinación falló para la evidencia que el modelo declaró, y el sistema la reemplaza por otra cosa que sí verifica, en vez de degradar el ítem.

**Escenario de falla** — el LLM extrae *"garantía de cumplimiento: 10%"* citando una frase que no existe en ningún chunk (alucinación de la cita). `_rescue_paragraph_citation` prueba con `item["valor"]` = `"10%"` — que tiene 3 caracteres y no llega a `CITATION_MIN_CHARS`, así que se descarta. Bien. Pero con `valor = "10% del monto adjudicado"` (24 caracteres), si esa cadena existe en algún chunk de esa página **por cualquier motivo** (p. ej. porque es el porcentaje de otra garantía), el ítem queda verificado con una cita que el modelo nunca vio como evidencia. El usuario recibe un dato con `extraction_status: success` y una cita que respalda otro hecho.

**Fix propuesto** — separar los conceptos en el modelo de datos: `citation_model` (lo que el LLM emitió, inmutable) y `citation_display` (la versión ensanchada para lectura). El rescate del caso 3 debería degradar a `partial` con una marca visible, no restaurar a `success`.

---

### ATR-03 · alta · Un ítem sin ninguna cita verificable conserva sus datos y su status "partial"

**Evidencia** — `extractors/base.py:887-892`

```python
if not any_verified:
    unverified_items += 1
    item["source_references"] = []
    if status == "success":
        item["extraction_status"] = "partial"
    item["_warning"] = "cita_no_verificada"
```

**Qué pasa a nivel extractor** — el ítem sobrevive con `valor` intacto, sin fuentes, marcado `partial` y con un `_warning` interno.

**Qué pasa después** — acá el pipeline **sí** se protege bien: `merge_node` llama a `_drop_items_without_sources` (`graph.py:718-731`) para las 8 categorías, que filtra `[item for item in items if list(item.get("source_references", []))]`. El ítem sin fuentes se descarta y la categoría baja a `partial`. **Verifiqué las 8 llamadas** (`graph.py:807-834`).

**Dónde queda el agujero** — el usuario ve la categoría como `partial` pero **no ve nunca cuántos ítems se descartaron ni por qué**. `_warning: "cita_no_verificada"` se pierde con el ítem. Y la diferencia entre "la categoría está parcial porque el pliego dice poco" y "está parcial porque el modelo alucinó tres ítems que tuvimos que tirar" es información de calidad que el operador necesita y que hoy solo existe en un log (`citation_grounding_check`, `base.py:894-901`).

**Escenario de falla** — un pliego donde el retrieval falló para causales de rechazo (por IDX-02, digamos). El LLM produce ítems plausibles a partir de contexto tangencial; todos fallan grounding; todos se descartan; la categoría queda `partial` con 1 ítem. El usuario interpreta "el pliego casi no tiene causales de rechazo". La señal correcta sería "no confíes en esta categoría".

**Fix propuesto** — propagar el conteo de descartes a `extraction_metadata` por categoría y mostrarlo en la UI como una advertencia de calidad ("2 de 5 hallazgos no pudieron respaldarse y fueron omitidos").

---

### ATR-04 · media · `block_id` solo se completa para una de las ocho categorías

**Evidencia** — el único lugar del código que escribe `block_id` en un `source_reference` es `_augment_identificacion_payload` (`base.py:739-763`):

```python
block_id = None
source_data = chunk.get("source", {})
if isinstance(source_data, dict):
    blocks = source_data.get("blocks", [])
    if blocks and isinstance(blocks, list) and blocks[0]:
        block_id = str(blocks[0].get("block_id") or blocks[0].get("para_id", ""))
...
"source_references": [{..., "block_id": block_id}]
```

Para las otras siete categorías, `block_id` solo puede venir del LLM — pero `_format_chunks` (`base.py:113-128`) **no expone ningún identificador de bloque**: el header solo lleva `Fragmento`, `Documento`, `Página`, `Sección`, `Tipo` y opcionalmente `Tabla`/`Fila`. El modelo no tiene forma de conocerlo.

Además, incluso donde se completa, se toma `blocks[0]` — el **primer** bloque del chunk, sin verificar cuál contiene la cita.

**Qué pasa** — `_item_source_stubs` (`synthesis.py:332-335`) y `_dedupe_narrative_sources` (`:303-305`) propagan `block_id` con cuidado, y el comentario de `_dedupe_narrative_sources` aclara que es "metadata, NO para agrupación". Pero el campo llega vacío en 7 de 8 categorías, y arbitrario en la octava.

**Escenario de falla** — no rompe nada hoy porque `highlight.py:483-485` decidió explícitamente ignorar `block_id` ("NUNCA marcar párrafo completo basándose en block_id (es solo metadata)"). Es un campo del contrato que atraviesa cuatro módulos y no tiene ningún consumidor. Costo de mantenimiento sin beneficio.

**Fix propuesto** — o se elimina del contrato, o se completa correctamente en `_verify_citation_grounding` (junto con `chunk_id`, ver ATR-01) tomando el bloque que efectivamente contiene la cita.

---

# CAPA 8 — Highlighting

## La cadena completa, y dónde se rompe

```
PDF block (Azure DI bounding_regions)
   ↓  _extract_bounding_boxes                       ✅ ok (salvo unidades, ING-03)
paragraph (para_id = (page, índice secuencial))
   ↓  _build_para_id_index / _enrich_blocks_with_para_id
   ⚠️  ROTURA 1 — ING-01: desalineación por membrete/pie
chunk (source.blocks[] con bbox)
   ↓  _merge_intermediate_blocks + create_chunks
   ⚠️  ROTURA 2 — CHK-02/CHK-03: piezas y children heredan bbox ajenos
índice Azure Search (campo 'source', JSON)
   ↓  search → _deserialize_source                   ✅ ok
retrieval (chunk recuperado)
   ↓  run_extractor → _verify_citation_grounding
   ❌  ROTURA 3 — ATR-01: se pierde la identidad del chunk
LLM evidence (citation)
   ↓  run_synthesis → _resolve_narrative_sources
   ❌  ROTURA 4 — SYN-02: si la evidencia no resuelve, se descarta la categoría entera
displayed source (narrative.sources[])
   ↓  compute_highlights_for_sources
   ⚠️  BIFURCACIÓN — HL-02: PyMuPDF en vivo tiene prioridad; los bbox de arriba
       solo se usan si PyMuPDF falla
highlight (x, y, width, height)
   ❌  ROTURA 5 — HL-01: el eje Y sale invertido
```

**Respuesta directa a tu pregunta:** la cadena se rompe en cinco puntos, pero el que hace que nada de lo anterior importe es el último. Aunque arreglaras ING-01, CHK-02, CHK-03 y ATR-01, el resaltado seguiría dibujándose en el lugar equivocado por HL-01.

---

### HL-01 · crítica · La conversión de coordenadas invierte el eje Y

**Evidencia** — `backend/analysis/extraction/highlight.py:298-307` (y el mismo bug repetido en `:340-348`)

```python
# Convertir coordenadas PyMuPDF (bottom-left) a top-left (estándar web)
regions = [
    {
        "x": float(rect.x0),
        "y": float(page_height - rect.y1),  # Conversión a top-left origin
        "width": float(rect.width),
        "height": float(rect.height),
    }
    for rect in text_instances
]
```

y el docstring que lo justifica (`:234-237`):

> *Las coordenadas retornadas usan origin top-left … **PyMuPDF internamente usa bottom-left**, pero esta función ya hace la conversión.*

**Qué debería pasar** — devolver `y` = distancia desde el borde superior de la página hasta el borde superior del rectángulo.

**Qué pasa** — **la premisa es falsa.** MuPDF normaliza el sistema de coordenadas del PDF a origen **top-left**: `page.rect` es `(0, 0, width, height)` con `y` creciendo hacia abajo, y `page.search_for()` devuelve `Rect` en ese mismo sistema. La "conversión" invierte una coordenada que ya estaba bien.

**Verificación empírica** — generé un PDF de 400×800pt con dos textos, uno arriba y otro abajo, y ejecuté la fórmula exacta del código:

```
ARRIBA_TOKEN: rect.y0=48.2  rect.y1=63.3  | y que devuelve el código = 736.7
ABAJO_TOKEN:  rect.y0=748.2 rect.y1=763.3 | y que devuelve el código = 36.7
```

El texto que está a 48pt del tope se emite como si estuviera a 737pt del tope. El que está al pie, como si estuviera arriba. **Espejado.**

Sobre una A4 real (595×842pt) con un heading a 78pt del borde superior:

```
texto real: y0=78pt desde el tope
y emitido:  749pt  →  el visor lo dibuja a 749pt del tope
error vertical: 671pt sobre 842pt de página
```

**Escenario de falla** — el usuario hace clic en "Garantía de mantenimiento de oferta: 1%" en la tarjeta de resultados. El visor abre la página correcta y dibuja el rectángulo de resaltado sobre el pie de página, encima de la numeración. Como el rectángulo tiene el `width`/`height` correctos y el `x` correcto, parece un resaltado legítimo — solo que sobre el texto equivocado. Y por HL-02 este es el camino **primario** en producción.

Corolario incómodo: si el frontend hoy "se ve más o menos bien", es porque está aplicando su propia corrección o ignorando `y`. Vale la pena verificarlo antes de tocar el backend, para no romper una compensación existente.

**Fix propuesto** — `"y": float(rect.y0)`. Un test que abra un PDF con texto conocido en la parte superior y verifique `y < page_height / 2`.

---

### HL-02 · alta · Dos sistemas de highlighting compitiendo; el que recibe toda la inversión es el que casi nunca corre

**Evidencia** — `highlight.py:436-458`

```python
pdf_path = (document_id_to_blob_path or {}).get(document_id)
if pdf_path:
    live_regions = compute_highlight_regions(pdf_path, page_number, citation, ...)
    if live_regions:
        source_copy["highlight_regions"] = live_regions
        ...
        enriched_sources.append(source_copy)
        continue                    # ← nunca llega al camino de bbox almacenado

if chunks_by_doc_page:
    # ... todo el matching contra source.blocks[].bbox
```

En producción `document_id_to_blob_path` **siempre está poblado**: `_build_document_mapping` (`graph.py:118-280`) descarga los PDFs a `/tmp/highlights-{analysis_id}/` vía `download_to_temp`.

**Qué pasa** — toda la maquinaria de bbox de las capas 1 y 2 (`_build_para_id_index`, `_enrich_blocks_with_para_id`, `merged_blocks`, `source.blocks`, los scripts de migración `add_bbox_field_to_index.py` y `add_blocks_field_to_index.py`, la columna `blocks` del índice) alimenta un camino que solo se ejecuta cuando PyMuPDF no encuentra la cita.

**Por qué importa** — desde el punto de vista de priorización, cambia todo. ING-01 (bbox desalineado) parece crítico hasta que se ve que su consumidor es un fallback. Y al revés: HL-01 parece un bug de conversión menor hasta que se ve que gobierna el 100% de los resaltados exitosos.

También significa que hay dos definiciones distintas de "dónde está esta cita" que nunca se comparan entre sí. Ninguna telemetría mide si coinciden.

**Fix propuesto** — decidir cuál es la fuente de verdad. Mi recomendación: PyMuPDF en vivo como primario (es más preciso: ubica la frase exacta, no el párrafo entero) con el bbox almacenado como fallback — o sea, el orden actual — pero entonces (a) arreglar HL-01 es prioridad absoluta, y (b) conviene evaluar si vale la pena seguir manteniendo toda la cadena de bbox de ingestion, o simplificarla a "página + fallback al párrafo".

---

### HL-03 · media · Normalización inconsistente entre dos checks contiguos de la misma función

**Evidencia** — `highlight.py:465-469` (filtro a nivel chunk)

```python
for chunk in matching_chunks:
    chunk_content = str(chunk.get("content", ""))
    # Match por contenido - citation debe estar en el chunk
    if citation not in chunk_content:        # ← comparación CRUDA
        continue
```

versus `highlight.py:511-516` (filtro a nivel block, 45 líneas más abajo)

```python
block_normalized = _normalize_for_search(block_text)
if citation_normalized in block_normalized:   # ← comparación NORMALIZADA
    matched_blocks.append(block)
```

**Qué pasa** — el filtro de entrada es estricto (respeta acentos, mayúsculas, espacios múltiples y saltos de línea) y el interno es tolerante. Una cita que difiere del `content` solo en el colapso de espacios —lo que ocurre sistemáticamente, porque `_build_context_citation` y `_widen_citation_with_chunk_context` construyen la cita con `" ".join(content.split())` mientras el `content` del chunk conserva los `\n` del maquetado— **nunca llega** al filtro interno.

**Escenario de falla** — una cita ensanchada por `_widen_citation_with_chunk_context` (ATR-02) tiene los saltos de línea colapsados a espacios; el `content` del chunk los tiene como `\n`. La comparación cruda de la línea 469 falla, se saltea el chunk, y la función loguea `highlight_no_blocks_available` — "no hay bloques para esta fuente". El fallback queda inutilizado justo para las citas que el propio pipeline reescribió.

**Fix propuesto** — usar `_normalize_for_search` en ambos lados de la línea 469.

---

### HL-04 · media · El camino por ancla no desambigua entre instancias múltiples

**Evidencia** — el camino exacto sí desambigua (`highlight.py:283-289`):

```python
if len(text_instances) > 1 and section_hint:
    text_instances = _select_best_instance(page=page, instances=text_instances, section_hint=..., ...)
```

pero el camino de ancla (`:332-356`) no:

```python
words = citation.split()
if len(words) >= 3:
    anchor = " ".join(words[:min(10, len(words))])
    anchor_instances = page.search_for(anchor)
    if anchor_instances:
        regions = [ {...} for rect in anchor_instances ]   # ← TODAS, sin filtrar
        return regions
```

**Qué pasa** — el ancla son las primeras 10 palabras de la cita. Ese prefijo es mucho más propenso a repetirse en la página que la cita completa (fórmulas jurídicas: *"El oferente deberá presentar, junto con su oferta, la siguiente"*). Cuando aparece N veces, se devuelven las N regiones.

**Escenario de falla** — el usuario hace clic en una cita y el visor resalta cuatro párrafos distintos de la página, uno de los cuales es el correcto. Peor que no resaltar nada, porque parece que el sistema está seguro.

**Fix propuesto** — aplicar `_select_best_instance` también en el camino de ancla, o devolver `[]` si hay más de una instancia y no se puede desambiguar.

---

### HL-05 · baja · `_normalize_for_search` está definida dos veces, idéntica

**Evidencia** — `highlight.py:23-49` y `highlight.py:179-205`. Byte por byte iguales, incluido el docstring. La segunda definición sombrea a la primera.

**Por qué lo incluyo** — no tiene impacto funcional, pero es la señal más clara de que este archivo no pasó por review. Es el archivo donde está HL-01.

**Fix propuesto** — borrar una.

---

### HL-06 · baja · Dos comentarios que contradicen el código, en el mismo archivo

**Evidencia**

1. `highlight.py:398` — docstring de `compute_highlights_for_sources`:
   > `document_id_to_blob_path: Mapeo document_id → ruta absoluta del PDF (NO usado)`

   Es el parámetro que gobierna el camino primario, en la línea 436. Sí se usa.

2. `highlight.py:290-296` — el log de desambiguación:
   ```python
   text_instances = _select_best_instance(...)     # devuelve 1 elemento
   logger.info(
       "highlight_multiple_instances_disambiguated",
       original_count=len(text_instances),          # ← siempre 1: se lee DESPUÉS de reasignar
       ...
   )
   ```
   `original_count` vale siempre 1. La telemetría de desambiguación no mide nada.

**Fix propuesto** — corregir el docstring; capturar `original_count` antes de la reasignación.

---

### HL-07 · baja · Rama muerta en `_build_document_mapping`

**Evidencia** — `graph.py:219-229`

```python
blob_storage = AzureBlobStorageAdapter(...)
...
# Local: acceso directo al filesystem
if hasattr(blob_storage, "root"):
    for doc in documents:
        blob_path = blob_storage.root / doc.blob_name
```

`AzureBlobStorageAdapter` no tiene atributo `root` (sus métodos son `upload`, `delete`, `download_to_temp`, `generate_download_url`). La rama nunca se ejecuta. Residuo del adaptador local eliminado (mismo origen que ING-05).

**Nota** — verifiqué también si `mapping[doc.id]` podía tener un desajuste de tipo con el `document_id` de los chunks (UUID vs str). **No lo tiene**: `Document.id` está declarado `Mapped[str] = mapped_column(String(36), ...)` en `documents/models.py:19`. Descarté ese falso positivo.

**Fix propuesto** — borrar la rama.

---

# Tabla de priorización

Orden sugerido de ataque. "Impacto" es sobre la calidad percibida de la respuesta; "esfuerzo" es la magnitud del cambio, no su riesgo.

| # | ID | Capa | Sev. | Impacto | Esfuerzo | Por qué en este orden |
|---|---|---|---|---|---|---|
| 1 | **HL-01** | 8 | crítica | Muy alto | Trivial (1 línea) | Todo resaltado exitoso está mal ubicado. Una línea, verificado empíricamente. Verificar antes si el frontend compensa. |
| 2 | **SYN-02** | 6 | crítica | Muy alto | Bajo (~5 líneas) | Categorías completas se muestran como "no encontrado" teniendo los datos. Es un fallback que falta. |
| 3 | **RET-01** | 4 | crítica | Alto | Trivial (1 línea) | Evidencia duplicada en el contexto → confidence inflada + slots de top_k desperdiciados. |
| 4 | **SYN-03** | 6 | crítica | Alto | Medio | 8 fetches redundantes + muestreo sesgado. Habilita SYN-02 y es el mayor costo de latencia del análisis. |
| 5 | **IDX-02** | 3 | crítica | Muy alto | Medio (reindex) | BM25 casi no aporta a la fusión híbrida. Confirmar H-1 antes. |
| 6 | **CHK-01** | 2 | crítica | Alto | Medio | Duplicación masiva en el índice; agrava #3, #4 y #5. Reproducido. |
| 7 | **ATR-01** | 7 | crítica | Alto | Medio | Guardar `chunk_id` convierte 3 búsquedas por texto en lookups. Habilita fixes de #2 y capa 8. |
| 8 | **IDX-01** | 3 | crítica | Alto | Medio (reindex) | Los encabezados no son buscables. Combinar con #5 en una sola migración. |
| 9 | **CHK-06** | 2 | alta | Alto | Bajo | El ancestro gana la clasificación. Probable causa raíz de "pliegos equivalentes se comportan distinto". |
| 10 | **SYN-01 + SYN-04** | 6 | crítica/alta | Alto | Medio | Sacar la transcripción de manos del LLM. Cierra estructuralmente #2 y la fuga de attribution. |
| 11 | **IDX-03** | 3 | alta | Medio | Bajo | Chunks stale al reanalizar. 1 línea + test. |
| 12 | **CHK-04** | 2 | alta | Medio | Bajo | Anexos que son solo carátula no existen en el índice. |
| 13 | **RET-02** | 4 | alta | Medio | Bajo | El fallback wildcard está siempre activo por accidente. |
| 14 | **CHK-05** | 2 | alta | Medio | Trivial | `None` en vez del tacho de basura. |
| 15 | **RET-03** | 4 | alta | Medio | Medio | Latencia: hasta ~1500 round-trips por análisis. |
| 16 | **ATR-02 + SYN-05** | 7/6 | alta/media | Medio | Medio | La cita mostrada no es la usada, y alimenta la confidence. Atacar juntos. |
| 17 | **CHK-02 + CHK-03** | 2 | alta | Medio | Medio | Precisión del resaltado. Vale la pena **después** de #1 y #7. |
| 18 | **HL-02** | 8 | alta | — | Decisión | Decisión de arquitectura, no fix. Determina si #17 e ING-01 valen la pena. |
| 19 | **ATR-03** | 7 | alta | Medio | Bajo | Señal de calidad al usuario, no corrección de dato. |
| 20 | **ING-01** | 1 | crítica | Bajo* | Bajo | *Bajo hoy porque es fallback (HL-02). Sube a alto si se decide priorizar bbox almacenado. |
| 21 | **CHK-07, CHK-08** | 2 | media | Medio | Bajo | Calidad de clasificación. Requiere un set etiquetado para calibrar. |
| 22 | **CTX-03, CTX-04** | 5 | media | Medio | Bajo | Honestidad hacia el usuario ("no analizado" ≠ "no encontrado"; conflictos visibles). |
| 23 | **HL-03, HL-04** | 8 | media | Bajo | Bajo | Solo relevantes si el fallback de bbox importa (ver #18). |
| 24 | Resto (ING-02..05, IDX-04/05, RET-04/05, SYN-06/07, ATR-04, HL-05..07, CTX-01/02) | — | media/baja | Bajo | Bajo | Limpieza y robustez. Agrupar en un PR de higiene. |

## Hallazgos relacionados entre sí

**Cadena A — "la categoría desaparece"**
`CHK-01` (chunks duplicados, +40-67% de conteo) → `SYN-03` (el tope de 1000 se alcanza antes, muestreo sesgado) → `SYN-02` (la evidencia no resuelve) → el usuario lee *"No se encontró información"*.
Arreglar SYN-02 corta la cadena de inmediato; arreglar CHK-01 y SYN-03 elimina la causa.

**Cadena B — "el retrieval no encuentra lo que está ahí"**
`IDX-01` (heading no searchable) + `IDX-02` (sin analizador español + glossary sin tildes) → BM25 aporta poco a la fusión → `RET-02` (fallback wildcard siempre activo) → chunks arbitrarios en el prompt de la categoría más crítica.
Los tres se atacan en una sola migración de índice + un cambio de datos.

**Cadena C — "el resaltado apunta mal"**
`ING-01` (bbox corrido) y `CHK-02`/`CHK-03` (bbox heredados) degradan el camino de fallback; `ATR-01` (sin chunk_id) fuerza a reconstruir por texto; `HL-03` rompe esa reconstrucción; y `HL-01` arruina el camino primario.
**Orden correcto:** primero HL-01 (primario), después HL-02 (decidir arquitectura), y recién entonces decidir si vale invertir en ING-01/CHK-02/CHK-03.

**Cadena D — "la confianza es circular"**
`ATR-02` (el pipeline ensancha la cita) → `SYN-05` (la longitud de cita suma confidence, tanto en el prompt como en el código) → el sistema se premia por una decisión propia.
Y `RET-01` (evidencia duplicada) alimenta el otro bonus, el de "dato consistente en múltiples fragmentos" (+0.2).

**Cadena E — "clasificación → boost → ruido"**
`CHK-06` (el ancestro gana) y `CHK-05` (tacho de basura) llenan `identificacion_procedimiento` → `_retrieve_with_category_priority` boostea ese ruido al extraer esa categoría → la carátula compite contra los considerandos.

---

# Hipótesis a confirmar

No las reporto como hallazgos porque no pude verificarlas solo con el código del repo.

### H-1 · ¿Qué analizador tiene realmente el campo `content` del índice?

El índice no se crea desde el repo — los scripts presentes solo **agregan campos** a un índice preexistente. Si `content` fue creado a mano en el portal de Azure con `es.microsoft` o `es.lucene`, la mitad de IDX-02 (el problema de acentos y stemming sobre `content`) desaparece; el campo `title`, creado por `update_azure_search_schema.py` sin `analyzer`, seguiría afectado en cualquier caso.

**Cómo confirmarlo, sin tocar código:**
```python
from azure.search.documents.indexes import SearchIndexClient
idx = client.get_index(settings.azure_search_index_name)
for f in idx.fields:
    print(f.name, f.type, "searchable=", f.searchable, "analyzer=", f.analyzer_name)
print("similarity:", idx.similarity)
print("semantic:", idx.semantic_search)
```
Y una prueba funcional de una línea: buscar `garantia` (sin tilde) contra un análisis que sepas que contiene "garantía" y ver si devuelve algo.

### H-2 · ¿Azure acepta `top=3000` o lo recorta?

`_search_azure` pide `top = max(top_k*3, 30)`, que con `top_k=1000` (SYN-03) da 3000. El SDK pagina con continuation tokens, así que probablemente traiga los 3000 en 3 páginas; pero si el servicio recorta a 1000, el comportamiento real de `_build_chunks_by_id_index` difiere de lo que el código supone. No cambia la conclusión de SYN-03 (que es sobre el muestreo sesgado y la repetición ×8), pero sí cambia el costo estimado.

### H-3 · ¿El frontend compensa la inversión de Y de HL-01?

Si el visor PDF hoy resalta más o menos donde corresponde, alguien tiene que estar invirtiendo el eje de nuevo del lado del cliente. Antes de aplicar el fix de una línea hay que revisar el componente del visor (`frontend/src/**`, el visor de la US 3.2) — si compensa, corregir solo el backend rompe el resaltado. No audité el frontend, así que no puedo afirmarlo.

### H-4 · ¿Cuál de los dos runtimes corre en producción?

Existen dos implementaciones paralelas del pipeline de indexación: `extraction/runner.py::extract_and_index` (SQL) y `analysis/cosmos_runtime.py::extract_and_index_cosmos`. `routes.py:331` usa la segunda solo cuando `persistence_mode == "cosmos_only"`, y el `.env.example` sugiere `cosmos_temporal`. Comparé las dos y **para retrieval/chunking/indexación son equivalentes** (ambas llaman a `create_chunks` → `generate_embeddings` → `upload_chunks` con los mismos argumentos, y ninguna hace cleanup — IDX-03 aplica a las dos). Pero difieren en el manejo de progreso, timeout y cancelación, y esa divergencia es una fuente estructural de drift que conviene resolver aunque hoy no produzca un bug de RAG.

---

## Notas de método

Falsos positivos que evalué y **descarté** tras la relectura exigida por la Regla 2 — los dejo anotados para que no se re-investiguen:

- **Colisión de `chunk_index` entre parent y children** (`chunking.py:1315-1354`). Verifiqué la aritmética paso a paso: parent=N, children=N+1..N+k, siguiente=N+k+1. No hay colisión.
- **El delimitador `=== CONTENIDO DEL PLIEGO ===` no existe.** El `_base_system.txt` lo referencia y parecía huérfano; un grep confirmó que las 8 plantillas de categoría lo emiten. La defensa contra inyección de prompt está bien delimitada.
- **Desajuste de tipos UUID vs str en `document_id_to_blob_path`.** `Document.id` es `String(36)`, no `UUID`. No hay desajuste.
- **El re-sort de `_search_azure:339-345` como reranking roto.** Es un no-op sobre una lista que Azure ya devuelve ordenada por el score RRF; el desempate léxico solo actúa en empates exactos. El comentario describe correctamente lo que hace. No es un hallazgo.
- **Ítems sin fuente llegando al usuario** (`base.py:887-892`). Parecía un agujero de grounding, pero `merge_node` los descarta con `_drop_items_without_sources` en las 8 categorías. Lo reformulé como ATR-03, que es un problema de *señalización* al usuario, no de datos incorrectos.

Herramientas de verificación usadas: ejecución directa de `_split_block_into_chunks` con los defaults de producción (CHK-01); instalación de `azure-ai-documentintelligence` e inspección de `DocumentParagraph` (ING-02); instalación de PyMuPDF y medición sobre PDFs generados (HL-01); conteo programático sobre `glossary.json` (IDX-02); grep exhaustivo de llamadores para RET-02, IDX-03 y la ausencia de reranker.

---

## Apéndice · Hallazgos surgidos durante la implementación (2026-08-14)

Estos no salieron de la auditoría original: aparecieron al implementar los fixes,
al medir sobre datos reales o al investigar los síntomas que fue reportando la
usuaria. Van acá para que no se pierdan.

### FE-01 · media · El bundle del frontend supera los 500 kB y arrastra el motor de PDF a toda la app

**Evidencia** — salida de `vite build`:

```
(!) Some chunks are larger than 500 kB after minification.
```

Medido en `node_modules`: `pdfjs-dist/build/pdf.min.mjs` pesa **419 kB** minificado
por sí solo. El worker (`pdf.worker.min.mjs`, 1 MB) no entra en ese chunk porque
`utils/pdfWorker.ts` lo importa con `?url` y queda como asset aparte.

**Qué pasa** — `PDFViewer` se importa de forma estática desde
`AnalysisDetailPage`, así que el motor de PDF viaja en el bundle principal. Se
descarga en el login y en el dashboard, que no lo usan.

**Impacto** — sólo primera carga: más espera antes del primer render, y se nota
en conexiones lentas. No afecta el rendimiento una vez cargada la app ni la
corrección de nada.

**Fix propuesto** — cargar el visor con `React.lazy` + `import()` dinámico en
`AnalysisDetailPage`, con un `Suspense` que muestre el mismo spinner que ya usa
el visor mientras carga. El motor de PDF pasa a bajarse recién al abrir el
detalle de un análisis. Son pocas líneas y no toca la lógica del visor.

**No hacerlo junto con cambios de comportamiento del visor**: si algo falla
después, conviene saber si fue el cambio de carga o el de lógica.

### PRM-01 — detectado acá, desarrollado y corregido más abajo

Los prompts por categoría contradicen el límite de cita del prompt base. La
entrada completa, con la medición y el fix, está al final del apéndice.

### CFG-01 · media · El bonus de confianza por cita larga quedó inalcanzable

`graph.py::calculate_confidence` suma +0.2 cuando la cita promedio supera los
100 caracteres. Con el techo en 120, ese bonus pasó de ser habitual a ser casi
imposible: baja sistemáticamente la confianza que ve el usuario en todas las
categorías, sin que haya cambiado la calidad de la evidencia. Hay que
recalibrarlo — o, mejor, revisar si "cita larga = más confiable" sigue teniendo
sentido ahora que las citas son cortas a propósito.

### GRF-01 · media · `datos_procedimiento` es la única categoría sin red de seguridad por ítem

`graph.py:916` arma `datos_procedimiento` desde `identificacion` sin filtrar, y
sólo se valida al construir `ExtractedData(**...)`. Un único ítem malformado ahí
tumba el análisis completo — exactamente lo que `_keep_schema_valid_items` evita
para las otras siete categorías.

### ATR-06 · baja · El ancla de recorte de cita mezcla dos sistemas de coordenadas

`_citation_anchor_position` calcula la posición sobre el texto NORMALIZADO
(NFKD, sin acentos) y la aplica sobre el texto ORIGINAL. Con acentos no hay
desvío porque la longitud se conserva, pero sí lo hay con descomposiciones de
compatibilidad frecuentes en texto extraído de PDF (la ligadura `ﬁ` → `fi`, `½`,
superíndices): la ventana se corre unos caracteres. Impacto bajo por el lead-in
de 45 caracteres, pero es una inconsistencia real — la tercera rama de esa misma
función (la de números) sí trabaja sobre el texto original.

### Estado de HL-02 — resuelto por eliminación

La auditoría planteaba HL-02 como una **decisión de arquitectura**: si el
resaltado debía confiar en el bbox almacenado por Azure Document Intelligence o
en la búsqueda viva sobre el PDF. Quedó resuelto de la forma más fuerte posible:
el camino de bbox almacenado se eliminó. Emitía el rectángulo del PÁRRAFO
completo (era la causa del "resaltado por párrafo"), su unidad no estaba
unificada (ING-03) y duplicaba una convención de coordenadas que ya había
divergido una vez (HL-01). Hoy hay un solo camino.

### Deuda preexistente del repositorio, no introducida por esta auditoría

- `tests/extraction/test_ai_search_indexing.py` no compila: `SyntaxError` en la
  línea 308 (`mock_settings.return_value.`).
- `tests/test_extraction_pipeline.py` no compila: `NameError`, falta
  `import pytest`.
- Quedan 7 tests en rojo de antes de esta auditoría, no relacionados con ninguno
  de los hallazgos. Están en el baseline contra el que se verificó cada fix.

### CHK-10 · media · El `except` ancho del loop de chunking convierte errores de código en pérdida silenciosa de datos

**Evidencia** — `extraction/chunking.py`, el `for block in ...` de `create_chunks`
termina en:

```python
except Exception as exc:  # noqa: BLE001
    logger.warning("chunking_block_skipped", ..., error=str(exc))
    continue
```

**Cómo apareció** — implementando CHK-02 dejé una variable mal en la rama de
tablas (`chunk_content`, que en esa rama no existe: la variable correcta es
`full_content`). El `NameError` no propagó: lo atrapó este `except`, se registró
como un `warning` por bloque, y **desaparecieron todos los chunks de tabla del
documento**. `create_chunks` devolvió una lista sin una sola tabla y sin fallar.

El bug puntual está corregido y lo detectó un test existente
(`test_large_table_split_by_size_limit`), pero el mecanismo que lo volvió
invisible sigue ahí.

**Por qué importa** — el `except` está bien pensado para lo que fue escrito: un
bloque con datos raros no debería tumbar el chunking del pliego entero. Pero no
distingue "este bloque tiene una forma que no esperábamos" de "el código tiene
un error": las dos cosas terminan en un warning y en un documento indexado al
que le faltan pedazos. Y como el resultado es un análisis *incompleto* y no un
análisis *fallido*, nada aguas abajo lo nota.

**Fix propuesto** — dos cosas, ninguna cara:

1. No atrapar `NameError`, `AttributeError` ni `TypeError`: son errores de
   programación, no datos raros. Deben propagar.
2. Contar los bloques salteados y, si superan un umbral (o si son > 0 en un
   documento que sí tenía bloques de ese tipo), registrar un `error` con el
   conteo — no un `warning` por bloque, que se pierde entre el ruido.

Aplica el mismo razonamiento a los otros `except Exception` anchos del pipeline:
el de `run_extractor` (que motivó el blindaje de `test_categoria_no_muere_por_un_item`)
y el de `compute_highlight_regions`.

---

### ATR-07 · alta · La cita ensanchada podía perder la cita que ensanchaba

**Estado: corregido (2026-08-14).**

`analysis/extraction/extractors/base.py::_build_context_citation`

Cuando una cita verificada queda por debajo de `CITATION_PREFERRED_MIN_CHARS`
(40), `_widen_citation_with_chunk_context` la ensancha con el texto que la rodea
en el chunk donde matcheó. El ensanchado se hacía con dos constantes ciegas —100
caracteres a la izquierda, 140 a la derecha— y el resultado se pasaba por
`clip_citation`, que recorta un **prefijo** de 120.

Las tres decisiones se cancelan entre sí. Con un núcleo de 33 caracteres, la
ventana queda de 273 y el núcleo vive en el offset 100; el prefijo de 120 se
queda con los primeros 120 de esa ventana, así que del núcleo sobreviven 20
caracteres y el resto se cae. Y como el retroceso de 100 no mira límites de
palabra, la cita arranca en mitad de una.

**Evidencia** — análisis `4b88641d-9df9-4a45-a44e-2e3e1494d8da`, categoría
`objeto_alcance`, fuente 3:

```json
"citation_llm":    "Item 3: 4 (cuatro) LCD KVM Switch",
"citation_origin": "ensanchada",
"citation":        "m 1: 4 (cuatro) Servidores de aplicaciones tipo XEN Item 2: 4 (cuatro) Servidores de base de datos. Item 3: 4 (cuatro)"
```

Reproducido carácter por carácter contra el código anterior. Lo que se le
muestra a la persona como evidencia del ítem 3 arranca en mitad de la palabra
"Item", enumera completos los ítems 1 y 2 —que no tienen nada que ver con el
dato— y **no contiene "LCD KVM Switch"**, que es exactamente lo que el ítem
afirma. El resaltado no es un problema aparte: sigue fielmente a la cita, así
que marca tres renglones equivocados del PDF. `citation_origin: "ensanchada"`
—instrumentación de ATR-02— es lo que permitió detectarlo.

**Por qué importa** — el resto del pipeline trata la cita como *la prueba* del
dato: el grounding la vuelve a verificar, `search_for` la busca en el PDF, y la
persona la lee para decidir si le cree a la síntesis. Una cita que ya no
menciona el dato pasa las tres cosas igual, porque sigue siendo texto literal
del pliego. Es la falla más silenciosa de esta capa: no rompe nada, sólo
muestra la evidencia equivocada.

**Fix aplicado** — `_build_context_citation` pasa a garantizar dos invariantes,
en vez de aproximarlos:

1. el resultado **siempre contiene** `content[start:end]`. Si el núcleo por sí
   solo excede el techo, se recorta el núcleo — nunca se lo reemplaza por texto
   vecino;
2. los dos bordes caen en límite de palabra (`_word_start` / `_word_end`).

El presupuesto de contexto pasa a derivarse del objetivo (`min_chars`) en vez de
ser 240 fijo, repartido un tercio antes del dato y el resto después, y se
devuelve contexto —primero el de la derecha— si el redondeo a palabra entera se
pasa del techo. Además `_widen_citation_with_chunk_context` descarta el
ensanchado si el resultado no contiene la cita original: ensanchar es agregar
contexto, no cambiar de cita.

Cubierto por `backend/tests/test_ensanchado_de_cita.py` (11 tests). Tres fallan
contra el código anterior. Suite backend: 445 passed / 7 failed (los 7 son de
base, ver más arriba).

---

### CHK-11 · alta · FIX #8 (encabezados cortados) nunca se ejecuta en producción: depende de un bbox que llega vacío

`extraction/chunking.py::_starts_on_same_line` ↔ `extraction/document_intelligence.py::_enrich_blocks_with_para_id`

`_merge_truncated_headings_with_body` (CHK-12, implementado el 2026-08-13)
reconstruye los encabezados que Document Intelligence parte al medio. Detecta el
caso de forma **estructural**: exige que el cuerpo empiece en la misma línea
visual que el encabezado, comparando los bbox de los dos bloques
(`_starts_on_same_line`). Fue una decisión deliberada —una propiedad del
documento, no del vocabulario— y está bien razonada.

El problema es la degradación. `_first_bbox_on_page` devuelve `None` cuando
`block["bbox"]` está vacío, `_starts_on_same_line` devuelve `False`, y el guard
de `_merge_truncated_headings_with_body` saltea la fusión. Sin bbox el fix no
falla: **no existe**.

**Evidencia** — en el mismo análisis, `/api/debug/chunks` devuelve
`"bbox": []` en *todos* los `source.blocks` de los 20 chunks. Y los dos chunks
que el fix tenía que arreglar siguen partidos:

| chunk | `title` | `content` (inicio) |
|---|---|---|
| 12 | `Artículo Nº 10: GAR` | `ANTÍA DE ADJUDICACIÓN: En caso de corresponder...` |
| 14 | `ARTÍCULO 12: PLA` | `ZO DE ENTREGA` (13 caracteres) |

Es literalmente el pliego y el artículo con los que se escribió el fix.
Verificado ejecutando `_merge_truncated_headings_with_body` sobre esos dos
bloques: con `bbox: []` devuelve los dos bloques intactos; con bbox devuelve
`Artículo Nº 10: GARANTÍA DE ADJUDICACIÓN`.

**Por qué importa** — la consecuencia documentada de CHK-12 sigue vigente: ni el
título ni el cuerpo contienen la palabra "garantía", el artículo es invisible
para BM25 y para el vector, y la categoría `garantias` puede responder
`not_applicable` sobre un pliego cuyo Artículo 10 se titula *GARANTÍA DE
ADJUDICACIÓN*. No es un resaltado corrido: es información legal equivocada.

Y hay un segundo efecto, más general: **ING-01 (bbox no persistido) dejó de ser
deuda cosmética**. Mientras el resaltado dependía de PyMuPDF, un bbox vacío no
se notaba. Ahora hay lógica de chunking que decide en función de él, en silencio.

**Pendiente de decisión** — no está determinado *por qué* el bbox llega vacío;
para eso hacen falta las dos líneas de log que ya emite el pipeline
(`para_id_index_built` con `bbox_coverage_pct` y `para_id_enrichment_complete`
con `match_rate_pct`) sobre una corrida real. Los tres candidatos, en orden de
probabilidad:

1. `_page_unit_scales` no cubre las páginas y `_extract_bounding_boxes` descarta
   todos los bbox por el `continue` de unidad desconocida — el camino que
   introdujo el propio fix ING-03. Discriminante: si fuera esto, las filas de
   tabla *también* saldrían sin bbox, porque comparten `unit_scales`;
2. desalineación del índice `(página, índice_secuencial)` entre los bloques del
   parser de markdown y `result.paragraphs` — daría cobertura parcial, no cero;
3. `result.paragraphs` vacío.

Independientemente de la causa, `_starts_on_same_line` no debería ser el único
signo: un fix que se desactiva solo, sin log ni error, es peor que un fix que no
está. Corresponde decidir entre restaurar el bbox (ING-01) o darle a CHK-12 una
señal textual de respaldo — y, en cualquier caso, registrar explícitamente
cuántas veces se saltea la fusión por falta de bbox.

---

### ING-06 · crítica · La comparación de unidad usaba `str()` sobre un enum: el 100% de los bbox se descartaba

**Estado: corregido (2026-08-14). Regresión introducida por el propio fix ING-03 del 2026-08-13.**

`extraction/document_intelligence.py::_page_unit_scales`

ING-03 agregó la conversión de unidades del bbox de Azure DI a puntos. La
decisión de escala se tomaba así:

```python
unit = str(getattr(page, "unit", "") or "").strip().lower()
if unit == "inch":
    scales[page_number] = _POINTS_PER_INCH
```

`DocumentPage.unit` no es un string: es `LengthUnit.INCH`, declarado como
`class LengthUnit(str, Enum)`. Es una subclase de `str` —de ahí que el código
pareciera correcto— pero en un enum de Python `Enum.__str__` le gana a
`str.__str__`, así que `str(LengthUnit.INCH)` devuelve `"LengthUnit.INCH"`, no
`"inch"`.

La comparación falla para **todas** las páginas de **todos** los documentos. El
diccionario de escalas queda vacío, y `_extract_bounding_boxes` toma su rama de
"unidad desconocida" —un `continue` que descarta el bbox antes de emitirlo—
para cada polígono del pliego.

**Evidencia** — `scripts/diagnostico_bbox.py` sobre el pliego real
(*Licitación Privada Servidores 2025*, 10 páginas):

```
document_intelligence_unsupported_bbox_unit  pages=[1..10]  units=['lengthunit.inch']

PASO 1 · unidades por página (10 páginas)
   unidades reportadas : {'LengthUnit.INCH': 10}
   páginas con escala  : 0 / 10

PASO 2 · paragraphs de Document Intelligence
   total paragraphs         : 161
   con bounding_regions     : 161
   con bbox SIN convertir   : 161
   con bbox CONVERTIDO a pt : 0

para_id_index_built          bbox_coverage_pct=0.0  paragraphs_with_bbox=0  total_paragraphs=161
para_id_enrichment_complete  match_rate_pct=0.0  matched=0  no_match=126  total_blocks=126
```

161 párrafos con polígono, 161 con bbox crudo, **0 después de convertir**. El
`logger.error` que el propio fix había dejado como red de seguridad se disparó
correctamente en las 10 páginas —`units=['lengthunit.inch']` es literalmente el
bug impreso— y no lo miramos.

**Por qué importa** — este es el origen de CHK-11: `_starts_on_same_line` no
podía devolver `True` nunca, así que `_merge_truncated_headings_with_body`
(CHK-12) quedó como código muerto desde el día en que se escribió. Un fix
desactivado por otro fix del mismo día.

**Fix aplicado** — `_normalized_length_unit` lee `.value` (el contrato del
enum) y, como red, descarta el prefijo `Clase.` si quedara alguno. Sirve igual
si el SDK pasa a devolver un `StrEnum`, un string pelado o un enum con otro
nombre de clase. Cubierto por `backend/tests/test_bbox_unidad_y_mapeo.py`,
incluido un test que fija la premisa (`str(LengthUnit.INCH) != "inch"`) para que
no vuelva a asumirse lo contrario.

**Lección de método** — el fix ING-03 tenía tests, y pasaban: construían las
páginas de prueba con `unit="inch"` como string. El test reproducía la
*intención* del SDK, no su *tipo*. Los fixtures de un adaptador de servicio
externo tienen que usar los tipos reales del SDK, no strings que se les
parezcan.

---

### ING-07 · alta · El índice bloque → bbox es posicional y no verifica que el texto coincida

**Estado: corregido (2026-08-14), junto con ING-06 porque sin esto el fix de ING-06 empeoraba las cosas.**

`extraction/document_intelligence.py::_build_para_id_index` / `_enrich_blocks_with_para_id`

El mapeo de coordenadas usa `(página, índice_secuencial)` como identidad: el
bloque *i* de una página recibe el bbox del párrafo *i* de esa misma página en
`result.paragraphs`. Es correcto sólo si el parser de markdown produce
exactamente un bloque por párrafo de DI — precondición documentada en el código
y reforzada por el fix C-2 del 2026-08-12.

En el pliego real no se cumple. Las 10 páginas tienen consistentemente **dos
párrafos más que bloques**:

```
pág 1:  5 bloques vs  7 paragraphs        pág 5: 16 bloques vs 18 paragraphs
pág 2: 21 bloques vs 23 paragraphs        pág 6: 20 bloques vs 22 paragraphs
pág 3: 18 bloques vs 20 paragraphs        pág 7:  3 bloques vs  5 paragraphs
pág 4: 17 bloques vs 19 paragraphs        pág 8: 20 bloques vs 22 paragraphs
```

Con ING-06 vigente esto era invisible: el bbox llegaba vacío, así que daba lo
mismo a qué párrafo apuntara. Arreglar ING-06 sin arreglar esto habría sido
peor que dejarlo roto — cada bloque habría recibido coordenadas de otro texto,
y `_starts_on_same_line` habría fusionado encabezados mirando la geometría
equivocada. Un mapeo corrido es peor que ninguno: uno se nota, el otro no.

**Fix aplicado** — el índice guarda también el texto del párrafo, y
`_enrich_blocks_with_para_id` lo compara con el del bloque antes de aceptar el
bbox. La comparación tolera lo que el parser sí cambia legítimamente
(normalización de espacios, unión de líneas, recorte de viñetas) mediante
contención en cualquier sentido o coincidencia de prefijo normalizado; rechaza
lo que importa, que es un índice corrido apuntando a otro párrafo. Los rechazos
se cuentan en `para_id_enrichment_complete` bajo `text_mismatch`.

Esto **no** resuelve la desalineación de fondo — sólo deja de mentir sobre
ella. Corresponde investigar qué dos párrafos por página emite DI y el parser
no (el candidato obvio es el encabezado/pie de página, que DI marca con
`role="pageHeader"` / `"pageFooter"`), y decidir si filtrarlos del índice o
alinear por `span.offset` en vez de por posición. Queda anotado como ING-08.

**Nota sobre CHK-11** — con estos dos fixes `_starts_on_same_line` vuelve a
poder evaluarse, pero **no está verificado** que resuelva los chunks 12 y 14 del
análisis `4b88641d`. En esta corrida de Document Intelligence el Artículo Nº 10
sale entero en un solo párrafo (`'Artículo Nº 10: GARANTÍA DE ADJUDICACIÓN: En
caso de corresponder, el importe de...'`, `para_id=(4, 12)`), sin el corte que
sí tenía el análisis indexado. Es decir: el corte de encabezado que motivó
CHK-12 no se reproduce en este documento hoy. Hay que reanalizar y volver a
mirar antes de dar CHK-11 por cerrado.

---

### Corrección a ING-07 (2026-08-14) — lo que afirmé no lo sostenía la medición

Al documentar ING-07 escribí que arreglar ING-06 sin verificar el mapeo *"habría
hecho que cada bloque recibiera coordenadas de otro texto"*. **Eso no era una
observación: era una inferencia a partir de los conteos por página, y la
medición la desmiente.**

Con ING-06 corregido, sobre el mismo pliego:

```
para_id_index_built          bbox_coverage_pct=100.0  paragraphs_with_bbox=161  total_paragraphs=161
para_id_enrichment_complete  match_rate_pct=100.0  matched=126  no_match=0  text_mismatch=0  total_blocks=126
```

**126 de 126 bloques mapeados, cero rechazos por texto.** La diferencia de dos
párrafos por página existe, pero los párrafos sobrantes caen *después* de todos
los bloques en el orden de lectura, así que el índice `(página, orden)` no se
corre: los índices 0..N-1 alinean y las dos entradas extra simplemente quedan sin
usar. La precondición del mapeo posicional se cumple.

La verificación de texto de ING-07 se conserva igual —cuesta una comparación de
prefijo por bloque y convierte una precondición implícita en un número
observable (`text_mismatch`)— pero hay que registrar que **no estaba corrigiendo
un error real en este documento**. Lo que corresponde decir es que el mapeo
estaba bien y ahora además está verificado.

El mensaje del diagnóstico que anunciaba "CANDIDATO 2" ante cualquier diferencia
de conteo era un falso positivo por la misma razón, y quedó condicionado a que
haya rechazos reales.

---

### ING-08 · baja · Document Intelligence emite dos párrafos por página que el markdown no produce

Consecuencia benigna hoy (ver ING-07), pero es una precondición que se cumple
por casualidad: si los párrafos sobrantes aparecieran al *principio* de la
página en lugar del final, el índice posicional se correría entero y —sin la
verificación de texto— cada bloque tomaría el bbox de su vecino.

El candidato son los `role="pageHeader"` / `"pageFooter"` de DI. Corresponde
filtrarlos explícitamente del índice, o alinear por `span.offset` en vez de por
posición, para que la corrección deje de depender de dónde caigan.

Prioridad baja: con `text_mismatch` en el log, el día que se rompa se va a ver.

---

### CHK-12 · abierto · verificado sobre datos reales: no fusiona nada indebido, y tampoco tiene qué fusionar

Con ING-06 corregido, `_merge_truncated_headings_with_body` se ejecutó por
primera vez sobre el pliego real:

```
PASO 5 · qué fusiona CHK-12 ahora que el bbox existe
   bloques antes : 126
   bloques después: 126
   no fusionó nada en este documento
   pares en la misma línea visual: ninguno
```

Dos conclusiones, y conviene no confundirlas:

1. **El criterio geométrico no produce falsos positivos.** Era el riesgo real de
   activar una función que nunca había corrido: una fusión equivocada pega dos
   textos que no van juntos, dentro del contenido indexado, sin dejar rastro.
   Sobre 126 bloques con bbox al 100%, cero pares pasan `_starts_on_same_line`.
   Se puede reanalizar sin miedo.

2. **CHK-12 sigue sin estar probado en positivo.** En esta corrida de Document
   Intelligence el Artículo Nº 10 sale entero en un solo párrafo
   (`para_id=(4,12)`), sin el corte que sí tenía el análisis `4b88641d`. El caso
   que motivó el fix no se reproduce hoy sobre el mismo PDF. No sabemos si DI
   varía entre corridas o si el análisis indexado vino de otra versión del
   documento. Queda **abierto**: hay que reanalizar y volver a mirar los chunks.

---

### HL-08 · baja · Rama inalcanzable y comentario que promete un fallback inexistente

**Estado: corregido (2026-08-14). Residuo del propio fix de HL-02.**

`analysis/extraction/highlight.py::enrich_sources_with_highlights`

Al eliminar el camino de bbox almacenado quedó `regions = []` sin ninguna
reasignación posterior, una rama `if regions:` inalcanzable con su propio
`logger.debug("highlight_from_azure_di_blocks")`, y un contador
`multiple_blocks` que ya no se incrementaba pero seguía publicándose en la
telemetría como `multiple_blocks_filtered`.

Peor que el código muerto era el comentario que sobrevivió intacto: decía que si
la búsqueda viva no encuentra la cita *"se cae al matching por bbox almacenado
de más abajo"*. Ese camino ya no existe. Es la misma clase de hallazgo que
HL-06: un lector razonable —o yo mismo dentro de dos semanas— concluye que hay
una red de seguridad que no está, y diagnostica mal el próximo problema de
resaltado.

**Fix aplicado** — se eliminó la rama y el contador, y el `logger.warning` del
camino sin regiones pasa a decir lo que realmente pasó, con los datos para
diagnosticarlo: `had_pdf`, `section_hint` y el preview de la cita. Antes decía
`"No blocks found for source"`, que describe un mecanismo que ya no se usa.

---

### PRM-01 · media · Los prompts por categoría enseñaban como ✅ lo que el prompt base marca como ❌

**Estado: corregido (2026-08-14).**

`analysis/extraction/prompts/*.txt`

`_base_system.txt` sección 3 pide citas de entre 40 y 120 caracteres y cierra
con un contraejemplo explícito de cita de párrafo. Pero los ejemplos de salida
de cinco categorías mostraban como salida correcta exactamente eso:

| categoría | largo | 
|---|---|
| `garantias` | **198** |
| `anexos_obligatorios` | 163 |
| `criterios_evaluacion` | 158 |
| `requisitos_admisibilidad` | 130 |
| `causales_rechazo` | 127 |

El de `garantias.txt` era casi palabra por palabra el ❌ del prompt base: los dos
textos empiezan igual ("Los oferentes deberán constituir una garantía...").

**Por qué importa** — un ejemplo pesa más que una regla: el modelo copia la forma
de la salida que ve. Y una cita de 198 caracteres no se descarta, entra a
`shorten_citation_to_evidence`, que elige una ventana de 120 alrededor del dato.
O sea, el prompt fabricaba trabajo para la maquinaria de recorte y ensanchado —
que es justamente donde apareció ATR-07.

**Fix aplicado** — se acortaron las cinco citas verificando programáticamente que
cada una siga siendo **subcadena contigua y literal** del fragmento del ejemplo.
Donde el ítem afirmaba más de lo que entra en 120 caracteres (una garantía con
monto, forma y vigencia; un método de evaluación con ponderación y puntaje
mínimo) el ejemplo pasa a mostrar **dos `source_references` cortas** en vez de
una larga — que es el patrón correcto y no estaba enseñado en ninguna parte. Se
agregó la regla al prompt base:

> La cita tiene que contener el `valor` del ítem. Los campos de `metadata` son
> secundarios: si alguno necesita su propia evidencia y no entra en los 120
> caracteres, **agregá un segundo `source_reference`** en vez de alargar el
> primero.

**Test de contrato** — `backend/tests/test_prompts_coherentes_con_el_esquema.py`
recorre los ocho prompts, extrae las citas de los ejemplos y las valida contra
las constantes reales del esquema. Cualquier ejemplo nuevo fuera de rango rompe
en CI y no en producción. Verificado por reversión: con la cita vieja de 198
caracteres, falla.

**Dos reglas que escribí y tuve que sacar** — vale anotarlas porque las dos
parecían obvias y las dos eran falsas:

1. *"toda cita de ejemplo ≥ 40 caracteres"*. Falso para la carátula: el
   `organismo_convocante` de un pliego es "Municipalidad de Rosario", 24
   caracteres, y no hay nada más que agregar que siga probando ESE dato.
   Exigirle 40 obligaría al modelo a rellenar con las líneas vecinas de la
   carátula — que es exactamente la falla de ATR-07. La regla quedó como: si la
   cita es más corta que el mínimo preferido, tiene que ser porque el dato mismo
   es corto (el `valor` está contenido en la cita).
2. *"toda cita contiene el `valor` del ítem"*. Falso en varias categorías, donde
   `valor` es una descripción normalizada y no una copia literal
   (`causales_rechazo` da `"No acompañar la garantía de mantenimiento de
   oferta"` sobre un pliego que dice `"Serán rechazadas... las ofertas que no
   acompañen..."`). Y además contradice el patrón de dos citas que acabo de
   introducir, donde la segunda respalda la `metadata`, no el `valor`. Se
   eliminó: un test que codifica una regla equivocada es peor que no tenerlo.

---

## Índice de estado (2026-08-14)

Los IDs `ING-06`, `ING-07`, `ING-08` y `CHK-12` del apéndice se renumeraron hoy:
pisaban a `ING-04`, `ING-05`, `ING-06` y `CHK-08` de la auditoría original. Si
tenías una nota con la numeración vieja, `ING-04 (enum de unidad)` ahora es
`ING-06`, `ING-05 (mapeo posicional)` es `ING-07`, y las menciones a `CHK-08` que
hablaban de `_merge_truncated_headings_with_body` son `CHK-12`.

**Método de este índice:** se cruzaron los IDs del documento contra las
anotaciones `FIX (auditoría …, hallazgo XXX-NN)` del código y los tests. Un fix
que haya entrado sin dejar el ID en un comentario aparecería como pendiente; los
casos de borde se verificaron a mano y están marcados.

### Cerrado — 33 hallazgos

Todos los `crítica` de las ocho capas, más CHK-01 a CHK-06, IDX-01/02/03/05,
RET-01/02/03, CTX-03/04, SYN-01 a SYN-05, ATR-01 a ATR-04, HL-01, HL-04, e
ING-03. Del apéndice: ATR-07, ING-06, ING-07, HL-08, PRM-01. HL-02 quedó
resuelto por eliminación (ver su nota).

### Abierto, esperando datos — 1

| ID | sev | qué falta |
|---|---|---|
| CHK-11 / CHK-12 | alta | La causa raíz (bbox vacío) está corregida por ING-06. Falta **reanalizar** y confirmar sobre los chunks que los encabezados cortados ya no aparecen. En la última corrida de DI el caso no se reproducía. |

### Calidad de extracción — 4. Necesitan criterio, no código

| ID | sev | qué es |
|---|---|---|
| CTX-01 | alta | El heading llega al prompt sólo dentro del header `[Fragmento: …, Sección: …]`, nunca pegado al texto. **Verificado hoy**: sigue así (`extractors/base.py:123`). |
| CHK-07 | media | El matching de términos multi-palabra es por subconjunto: sin orden ni adyacencia. |
| CHK-08 | media | La fórmula de densidad hace lo contrario de lo que documenta y satura con un solo match. |
| CHK-09 | media | La fusión de headings partidos entre páginas tiene un disparador demasiado laxo. |

Los tres de `CHK` son la misma decisión: **clasificación de chunks**. No conviene
tocarlos sin un set de pliegos etiquetado a mano, porque no hay forma de saber si
un cambio mejora o empeora. Es el único ítem del backlog que necesita trabajo
previo tuyo, no mío.

### Con fix propuesto, sin implementar — 6

| ID | sev | por qué importa |
|---|---|---|
| CHK-10 | media | El `except Exception` ancho del chunking convierte errores de código en pérdida silenciosa de datos. **Ya nos mordió una vez** en esta implementación: se tragó un `NameError` y produjo un documento sin ningún chunk de tabla. |
| GRF-01 | media | `datos_procedimiento` es la única categoría sin red de seguridad por ítem. |
| CFG-01 | media | El bonus de confianza por cita larga quedó inalcanzable tras el límite de 120. Código muerto que confunde. |
| FE-01 | media | El bundle del frontend pasa los 500 kB y arrastra el motor de PDF a toda la app. Lazy-load del visor. |
| ATR-06 | baja | `_citation_anchor_position` calcula el ancla sobre el texto normalizado y la usa como índice del original. |
| ING-08 | baja | Los dos párrafos por página que DI emite y el markdown no. Benigno hoy, por dónde caen. |

### Higiene — 13

`ING-02` (span vs spans), `ING-04` (filas de tabla que cruzan páginas), `ING-05`
(perfil development inexistente), `IDX-04`, `RET-04`, `RET-05`, `CTX-02`,
`SYN-06` (**verificado hoy**: el umbral sigue en 12), `SYN-07`, `HL-03`,
`HL-05` (**verificado hoy**: `_normalize_for_search` sigue definida dos veces),
`HL-06`, `HL-07`.

Ninguno cambia lo que ve la persona. Son consistencia interna y comentarios que
mienten — que es justo la clase de cosa que hizo perder tiempo dos veces en esta
implementación (HL-08, y la lección de método de ING-06).

### Deuda preexistente del repositorio

Dos archivos de test que no compilan y 7 fallos de base, ninguno introducido por
esta auditoría. Detalle en su sección.

---

## Apéndice II · Hallazgos del PET de Bancor (2026-08-14)

Segundo pliego analizado: *Pliego de Especificaciones Técnicas — Solución
Integral de Nube Privada On-Premise*, Banco de la Provincia de Córdoba.
Análisis `f33897ba-298d-439e-9d7e-ebc9f8830964`. Estructura muy distinta al de
Rosario: 45 páginas, tabla de contenidos, membrete con logo en todas las
páginas, numeración decimal de secciones (1.1, 3.1.1, 5.3) y varias tablas.

**Falso positivo descartado primero.** `total_chunks: 20` con el último chunk en
la página 10 parecía un corte de la extracción. No lo es: el endpoint de debug
devuelve `total_chunks = len(chunks)` sobre un `top=limit` que por defecto vale
20, y no expone `limit` en `filters`. Reporta una página como si fuera el total.
Anotado como **DBG-01** (baja) — conviene arreglarlo porque dependemos de ese
endpoint justamente para diagnosticar.

---

### ING-09 · alta · La identidad bloque → párrafo era posicional y se rompe con cualquier figura o tabla

**Estado: corregido (2026-08-14).**

`extraction/document_intelligence.py::_enrich_blocks_with_para_id`

El bloque n-ésimo de una página tomaba el bbox del párrafo n-ésimo de
`result.paragraphs`. Eso exige que el parser de markdown produzca exactamente un
bloque por párrafo de DI, y deja de cumplirse en cuanto la página tiene una
figura o una tabla: DI las incluye en `paragraphs`, el parser las emite aparte
(`table_ref`) o las descarta, y desde ahí los dos índices corren desfasados
hasta el final de la página.

En el pliego de Rosario esto no se vio porque los párrafos sobrantes caían al
final de cada página (ver la corrección a ING-07). Acá el logo del membrete está
en **todas** las páginas y la tabla de contenidos ocupa la página 2.

**Evidencia** — sobre los 20 chunks devueltos: de **86 bloques de párrafo, sólo
3 conservaron bbox**. Y son exactamente los tres anteriores a la primera figura
o tabla de su página: `[1,0]`, `[2,0]` y `[2,1]`. Todo lo posterior —
`[3,0]`…`[3,10]`, `[4,2]`…`[4,12]`, `[9,0]`…`[9,21]`, `[10,0]`…`[10,15]` — salió
con `"bbox": []`.

**La verificación de ING-07 hizo exactamente su trabajo.** Los 83 bloques que
quedaron sin bbox no se perdieron: se rechazaron porque el texto no coincidía.
Sin esa verificación, esos 83 habrían llevado en silencio las coordenadas de
otro párrafo, y `_starts_on_same_line` (CHK-12) habría decidido fusiones de
encabezado mirando geometría ajena. Es la primera vez que una guarda de esta
auditoría atrapa algo en producción.

**Fix aplicado** — la identidad pasa a ser el **texto**, que es lo que de verdad
identifica al párrafo, con dos controles que la posición daba gratis y el texto
no:

- `usados` impide que dos bloques se lleven el mismo párrafo;
- `cursor` fuerza el orden de lectura, que es lo que desambigua un texto
  repetido en la misma página — el "BANCOR" del membrete aparece dos veces.

Se busca primero hacia adelante desde el cursor y el barrido completo queda como
red para cuando DI reordena respecto del markdown. `para_id` pasa a ser el
índice REAL del párrafo, no un contador secuencial: ahora significa algo.

Además `_same_text` exige igualdad exacta por debajo de 8 caracteres. Con
contención, en una tabla de contenidos —una página llena de números sueltos— el
bloque `"4"` matcheaba el párrafo `"41"`.

Cubierto por `tests/test_bbox_unidad_y_mapeo.py` (15 tests). Tres fallan contra
el matcheo posicional. Suite: 487 passed / 7 failed (los 7 de base).

**Segunda vez que un fixture desactualizado esconde el bug.** El cambio hizo
fallar dos tests de `test_bbox_units.py` que construían el índice a mano con la
forma vieja (una lista de bbox pelada en vez de `{"bbox": …, "content": …}`).
Con esa forma el test pasaba **vacío**: no verificaba nada. Es la misma trampa
que dejó pasar ING-06 durante un día entero. Quedó una nota en ese archivo.

---

### Pendientes de este pliego, sin implementar

| ID | sev | qué es |
|---|---|---|
| ~~CHK-13~~ | alta | **CORREGIDO (2026-08-14), ver abajo.** La tabla de contenidos se indexa como contenido. Los chunks 3, 4 y 5 son el índice puro: 2.011, 94 y 290 caracteres de `col_1: 3.1.2. Virtualización / col_2: 12`. El chunk 4 dice literalmente `col_1: 5.3. Garantía y servicio post-venta`. Una consulta sobre garantías lo recupera con buen score y no prueba nada: es ruido de retrieval que compite con la evidencia real, en las ocho categorías. |
| ~~CHK-14~~ | media | **CORREGIDO (2026-08-14), ver abajo.** Los chunks de tabla duplican entero el párrafo anterior. El contenido del chunk 15 (953 caracteres) aparece completo otra vez al principio del chunk 16; el del 13 (190) en el 14. `_preceding_table_context` toma el párrafo previo entero en vez de una línea introductoria. Infla el índice y gasta presupuesto de contexto dos veces por el mismo texto. |
| ~~CHK-15~~ | media | **CORREGIDO (2026-08-14), ver abajo.** El membrete de página se usa como contexto de tabla. El chunk 2 es un chunk entero de 40 caracteres que dice `BANCO DE LA PROVINCIA DE CÓRDOBA / BANCOR`, y ese texto encabeza los chunks 3 y 4. El "párrafo que introduce la tabla" resultó ser el logo. |
| ~~CHK-16~~ | media | **CORREGIDO (2026-08-14), ver abajo.** Los encabezados decimales no se normalizan. `section_path` del chunk 12: `… > 1.6. Visita técnica obligatoria > 1.7. Plazo de entrega`. Son hermanos. Verificado: `_normalize_numbered_heading_levels` usa `^(\d+)\.\s+[A-ZÁÉÍÓÚÑ]`, que matchea `1. Generalidades` pero **no** `1.6.`, `3.1.1.` ni `5.3.` — o sea, no toca ningún encabezado decimal, que es toda la numeración de este pliego. |
| ~~DBG-01~~ | baja | **CORREGIDO (2026-08-14).** `/api/debug/chunks` reporta `total_chunks` = la página devuelta, no el total, y no expone `limit` en `filters`. |

---

### CHK-13 · alta · La tabla de contenidos se indexaba como si fuera contenido

**Estado: corregido (2026-08-14).**

`extraction/chunking.py::_drop_index_listings`

El índice del PET de Bancor produjo tres chunks — 2.011, 94 y 290 caracteres —
de la forma `col_1: 3.1.2. Virtualización / col_2: 12`. Uno de ellos dice
literalmente `col_1: 5.3. Garantía y servicio post-venta`.

El problema no es el volumen: es que el índice **nombra** las secciones sin
**contenerlas**. Una consulta sobre garantías lo recupera con buen score porque
comparte todas las palabras del encabezado, y después no prueba nada. Compite
con la evidencia real en las ocho categorías, y en atribución produce una cita
que remite a un renglón de un índice.

**El riesgo del fix es el inverso y es peor.** Descartar contenido real —un
cronograma escalonado, una planilla de cotización— sería mucho más grave que
conservar ruido. Por eso la detección exige **cinco** condiciones a la vez sobre
el grupo de bloques:

1. cinco entradas o más;
2. ≥75% terminan en un número suelto de hasta tres dígitos;
3. esos números no decrecen y hay al menos tres distintos;
4. el mayor apunta **hacia adelante** y **no supera la cantidad de páginas del
   documento** — o sea, son páginas de este pliego recorridas en orden;
5. ≥60% de las entradas empiezan con numeración de sección (`1.`, `3.1.2.`),
   con el punto final obligatorio.

Las tres primeras las cumple un cronograma escalonado ("Etapa 1: 30, Etapa 2:
60, Etapa 3: 90…"), que es el falso positivo que más caro saldría porque son
plazos y hay que extraerlos. Las dos últimas existen para descartarlo. El punto
final de la condición 5 es lo que separa `1. Generalidades` de `1 Plataforma de
software`, la columna *Ítem* de una planilla de cotización.

Se evalúa **la tabla entera**, no cada fila: el índice de Bancor se parte en dos
chunks por tamaño y la segunda mitad queda con una sola fila —justo la de
garantías— que sola no parece nada. Y también se evalúan las corridas de
párrafos consecutivos de una misma página, porque en la página 3 el índice deja
de venir como tabla y cada entrada es un párrafo, con el número de página a
veces como bloque aparte.

Lo descartado se registra con `logger.info("indice_del_pliego_descartado", …)`
incluyendo conteo, páginas y una muestra — CHK-10: nada se descarta en silencio.

Cubierto por `backend/tests/test_indice_del_pliego.py` (14 tests), de los cuales
**seis son guardas** sobre estructuras que se le parecen y tienen que
sobrevivir. Suite: 501 passed / 7 failed (los 7 de base).

**Un error propio, atrapado por un test existente.** La primera versión hacía
`(block.get("table_ref") or {}).get("table_id")`, asumiendo que `table_ref` es
un dict. El pipeline lo produce así, pero varios llamadores lo pasan como string
pelado, y eso reventaba con `'str' object has no attribute 'get'`. Lo atrapó
`test_create_chunks_siguiente_bloque_no_colisiona_con_indices_de_children`.

Vale marcar por qué tuvimos suerte: el error ocurrió en `_to_intermediate_blocks`,
**fuera** del `except Exception` ancho de CHK-10. Adentro del loop de chunking,
ese mismo `AttributeError` se habría tragado en silencio y el resultado habría
sido un documento indexado sin ninguna tabla — exactamente lo que pasó con el
`NameError` de `_blocks_data_for`. Es la segunda vez que ese `except` está a un
paso de convertir un error de tipos en pérdida de datos. **CHK-10 sube de
prioridad.**

---

### CHK-10 · media→alta · El `except` ancho del loop de chunking convertía errores de código en pérdida silenciosa de datos

**Estado: corregido (2026-08-14).**

`extraction/chunking.py::create_chunks`

El `except Exception` del loop está bien pensado para lo que fue escrito: un
bloque con datos raros no debería tumbar el chunking del pliego entero. Pero no
distinguía *"este bloque tiene una forma que no esperábamos"* de *"el código
tiene un error"*, y las dos cosas terminaban en un `warning` por bloque y en un
documento indexado al que le faltan pedazos.

Lo que lo hace grave es que el resultado es un análisis **incompleto**, no un
análisis **fallido**. Aguas abajo se ve idéntico a uno completo: la persona
recibe una respuesta con menos evidencia y ninguna señal de que falta algo.

**No es hipotético: pasó dos veces durante esta misma auditoría.**

1. Un `NameError` —una variable mal escrita en la rama de tablas de
   `_blocks_data_for`— produjo un documento indexado con **cero chunks de
   tabla**. Lo detectó un test, no el sistema.
2. Un `AttributeError` —asumir que `table_ref` es siempre un dict, en la primera
   versión de `_drop_index_listings` (CHK-13)— estuvo a un paso de lo mismo, y
   sólo se vio porque explotó en `_to_intermediate_blocks`, **fuera** de este
   `try`. Un metro más adentro y habría sido el mismo incidente.

En los dos casos el análisis habría terminado "bien".

**Fix aplicado** — las dos cosas que proponía el hallazgo:

1. `NameError`, `AttributeError` y `TypeError` propagan. No hay dato de un
   pliego que produzca un `NameError`: los tres son siempre errores de
   programación. El resto de las excepciones se sigue atrapando, que es la razón
   de ser del `except`.
2. Los bloques salteados se cuentan y se reportan **agregados en nivel `error`**
   (`chunking_blocks_skipped_total`, con páginas y tipos de error), no sólo como
   un warning por bloque que se pierde entre el ruido. `chunking_completed`
   también publica `bloques_saltados`.

Cubierto por `backend/tests/test_errores_de_chunking_no_se_tragan.py` (7 tests),
dos de ellos guardas de que el `except` sigue haciendo lo que fue escrito para
hacer. Cinco fallan contra el código anterior. Suite: 508 passed / 7 failed (los
7 de base).

**Queda pendiente el mismo razonamiento en los otros `except Exception` anchos
del pipeline**: `run_extractor` (`extractors/base.py`), `compute_highlight_regions`
y los cuatro de `graph.py`. Son el mismo patrón y el mismo riesgo, pero cada uno
tiene un contrato distinto con su llamador y conviene mirarlos de a uno.

---

### CHK-14 · media · Los chunks de tabla se llevaban pegado el párrafo anterior entero

**Estado: corregido (2026-08-14).**

`extraction/chunking.py::_preceding_table_context` → `_introductory_tail`

La función existe para que la frase que presenta una tabla ("La evaluación se
realizará según la siguiente tabla:") no quede separada de las filas que
explica. Devolvía `previous["content"]`.

El problema es **cuándo** corre: para entonces el bloque previo ya pasó por
`_merge_intermediate_blocks` y es la fusión de todos los párrafos de su sección.
Así que la tabla no se llevaba la frase introductoria: se llevaba la sección
completa.

**Evidencia** — el contenido del chunk 15 (953 caracteres) aparece **entero**
otra vez al principio del chunk 16, que es su tabla. Lo mismo entre el 13 y el
14. Ese texto queda indexado dos veces, ocupa lugar dos veces en el presupuesto
de contexto del prompt, y hace que dos chunks compitan entre sí en retrieval
diciendo exactamente lo mismo.

**Fix aplicado** — se toma el **último párrafo** del bloque previo, con un tope
de 300 caracteres y recorte por el final en borde de oración o de palabra.

El último párrafo no es sólo el más corto: es el correcto. En el chunk 15 es
`"PLATAFORMA INTEGRADA Y GESTIÓN CENTRALIZADA DE NUBE PRIVADA: BROADCOM VMWARE
CLOUD FOUNDATION 9.1 O SUPERIOR"` — exactamente el encabezado de la tabla de
licencias que sigue. Los 850 caracteres previos hablan de otra cosa. El contexto
mejora y además pesa 108 caracteres en vez de 953.

Cubierto por `backend/tests/test_contexto_de_tabla.py` (10 tests).

---

### CHK-15 · media · El membrete de página se indexaba como contenido

**Estado: corregido (2026-08-14).**

`extraction/chunking.py::_drop_repeated_page_furniture`

`_detect_repeated_heading_boilerplate` ya filtra el membrete cuando Document
Intelligence lo marca como **encabezado** — fue el caso del pliego de Rosario.
Su propio docstring aclara que un párrafo de cuerpo repetido no entra en ese
chequeo. En el PET de Bancor el membrete viene exactamente así, como párrafo.

**Evidencia** — el chunk 2 es un chunk entero de 40 caracteres que dice
`BANCO DE LA PROVINCIA DE CÓRDOBA / BANCOR`, y ese mismo texto encabeza los
chunks 3 y 4 como si fuera la frase que introduce sus tablas.

**Fix aplicado** — se descartan los párrafos que cumplen las dos condiciones a
la vez: **cortos** (≤120 caracteres) y **repetidos en la mayoría de las
páginas** (≥60%, mínimo 3). Una cláusula real del pliego no cumple las dos: si
se repite mucho es porque es corta y decorativa, y si tiene contenido es larga.
Las filas de tabla y los encabezados quedan fuera del chequeo — los encabezados
tienen su propio detector, con lógica de recorte parcial que no conviene
duplicar. Lo descartado se registra (CHK-10).

Cubierto por `backend/tests/test_membrete_de_pagina.py` (9 tests), cinco de
ellos guardas.

**Tercera aparición del fixture débil.** Dos de estos tests pasaban **vacíos**
en la primera versión: sin el filtro, el membrete se fusiona con el párrafo de
cuerpo siguiente y nunca queda como chunk propio, así que la aserción se cumplía
por accidente. Sólo fallaba 1 de 9 al revertir. Hubo que reproducir la
estructura real de Bancor —el membrete inmediatamente antes de la tabla, sin
párrafo en el medio— para que los tres tests detectaran de verdad. Es el mismo
patrón de ING-06 y de `test_bbox_units.py`: **un test que no falla al revertir
el fix no está probando el fix.** Conviene que la reversión sea parte del
protocolo y no una verificación ocasional.

Suite: 527 passed / 7 failed (los 7 de base).

---

### CHK-16 · media · Los encabezados con numeración decimal no se normalizaban nunca

**Estado: corregido (2026-08-14).**

`extraction/chunking.py::_normalize_decimal_heading_levels`

`_normalize_numbered_heading_levels` usa `^(\d+)\.\s+[A-ZÁÉÍÓÚÑ]`, que matchea
"1. Generalidades" pero **no** "1.6.", "3.1.1." ni "5.3.". Verificado
ejecutando el regex: no toca **ningún** encabezado decimal — que es toda la
numeración del PET de Bancor. La jerarquía quedaba siendo la que Azure DI
infirió del tamaño de la tipografía.

**Evidencia** — el `section_path` del chunk 12:

```
PLIEGO … > 1. Generalidades > 1.6. Visita técnica obligatoria > 1.7. Plazo de entrega
```

`1.6` y `1.7` son hermanos, no padre e hijo. Ese path alimenta el `section_hint`
que desambigua los resaltados en el PDF (ATR-01/HL-04) y el contexto que ve el
redactor de la síntesis, así que una jerarquía inventada se propaga a las dos
puntas.

**Fix aplicado** — un pliego que numera sus secciones está **declarando** la
jerarquía: "3.1.2." dice, sin ambigüedad, que cuelga de "3.1", que cuelga de
"3". Eso le gana a lo que DI infirió. El nivel pasa a ser
`base + profundidad - 1`, donde `base` es el nivel que ya tienen los encabezados
de primer nivel (o se deduce del decimal más chico, para un anexo que arranca
directamente en "4.1.").

Sólo se tocan los de profundidad ≥ 2: los de primer nivel los sigue manejando
`_normalize_numbered_heading_levels`, que además usa la consecutividad como
señal y esa información acá no está. El punto final del regex es obligatorio,
por la misma razón que en CHK-13: sin él, "1 Plataforma de software" —la columna
*Ítem* de una planilla— contaría como encabezado.

Cubierto por `backend/tests/test_jerarquia_decimal.py` (10 tests, cinco fallan
al revertir). Suite: 537 passed / 7 failed (los 7 de base).

---

### DBG-01 · baja · El endpoint de debug reportaba una página como si fuera el total

**Estado: corregido (2026-08-14).**

`debug/chunks_viewer.py`

Devolvía `total_chunks = len(chunks)` sobre un `top=limit` que por defecto vale
20, y no exponía `limit` en `filters`. Diagnosticando el PET de Bancor eso hizo
parecer, por un rato, que la extracción se había cortado en la página 10 de 45.

Ahora `total_chunks` es el conteo real del índice (`include_total_count`), se
agregan `returned_chunks` y `truncated`, y `limit` aparece en `filters`. Es una
herramienta de diagnóstico: que mienta sobre el tamaño de lo que muestra es
justamente lo que no puede hacer.

---

### CTX-01 · corrección del índice de estado (2026-08-14)

En el índice de estado listé CTX-01 como pendiente. **No lo está, y el propio
hallazgo lo dice**: su sección termina en *"Fix propuesto — ver IDX-01. No hay
nada que corregir en `_format_chunks`."* CTX-01 nunca fue un hallazgo
independiente; era la confirmación de que el problema estaba en la indexación y
no en la construcción del contexto.

IDX-01 está implementado y verificado hoy: `extraction/ai_search.py` declara
`_REQUIRED_SEARCHABLE_TEXT_FIELDS = ("content", "title", "section_path",
"heading_path")` y `_assert_index_contract` **falla el arranque** si alguno no
es `searchable`. El heading es buscable por BM25.

El índice de estado marcaba CTX-01 como pendiente porque el cruce se hacía
buscando el ID en el código, y un hallazgo que se cierra a través de otro no
deja su propio rastro. Es una limitación del método, ya anotada ahí; queda acá
el caso concreto.

---

### CTX-02 · media · Los chunks recuperados entraban completos al prompt, sin corte por relevancia

**Estado: corregido (2026-08-14).**

`analysis/extraction/extractors/base.py::_drop_low_relevance_chunks`

Se recuperaba `category_top_k` y sólo se recortaba por presupuesto de tokens. El
chunk de la posición 35 —con un score de RRF típicamente la mitad del primero—
entraba al prompt con el mismo peso visual que el primero.

Dónde duele: una categoría que en ESE pliego no tiene evidencia real —
`criterios_evaluacion` en un pliego que adjudica por menor precio sin matriz de
puntajes— igual llenaba sus 25-35 chunks con secciones tangenciales. Al modelo
se le pide ser "un analista experto que reconoce el concepto aunque el
vocabulario cambie", y después se le da mucho material del cual construir un
criterio que el pliego no tiene. La instrucción de no inventar está; la presión
del contexto va en contra.

**Fix aplicado** — corte relativo al mejor score de esa consulta (los scores de
RRF no son comparables entre consultas, así que un umbral absoluto descartaría
todo en una y nada en otra), **antes** del recorte por presupuesto: al revés, el
presupuesto se gastaría en la cola irrelevante.

El corte es deliberadamente tímido, porque **el error caro es el inverso**.
Descartar el chunk que sí tenía el dato reproduce exactamente la falla que esta
auditoría viene persiguiendo: una categoría respondiendo "no encontrado" sobre
un pliego que sí lo dice. Tres salvaguardas:

- los `_RELEVANCE_MIN_CHUNKS = 10` de mejor score entran **siempre**, sin mirar
  el umbral;
- un chunk sin `search_score` —o con un score no numérico— no se juzga: no tener
  el dato no puede costar el chunk;
- el umbral es `0.4 × mejor_score`, no la mitad. Con RRF (`k=60`), un chunk que
  encontró **sólo** el vectorial en la posición 3 puntúa ~0.48 del máximo: con
  un corte en 0.5 se perdería, y es justo el caso donde el vector aporta lo que
  BM25 no ve.

El piso se cuenta **por score y no por posición**, porque la expansión
children→parent puede alterar el orden de la lista.

Lo descartado se registra con los scores (`score_max`, `score_umbral`,
`score_descartado_max`) para poder calibrar el ratio sobre datos reales en vez
de discutirlo en abstracto — es lo que no pude medir antes de implementarlo.

Cubierto por `backend/tests/test_corte_por_relevancia.py` (11 tests, seis de
ellos guardas del piso; cinco fallan al revertir). Suite: 548 passed / 7 failed
(los 7 de base).

---

### CHK-07 · media · El matcheo de términos multi-palabra ignoraba orden y adyacencia

**Estado: corregido (2026-08-14).**

`extraction/chunking.py::_term_appears_in`

Un término de varias palabras se descomponía en un **conjunto** de tokens y
matcheaba si todos aparecían en cualquier lugar del chunk, en cualquier orden y
a cualquier distancia. `"mantenimiento de oferta"` se volvía
`{mantenimiento, de, oferta}`, y la palabra "de" está en el 100% de los chunks
en castellano: en la práctica alcanzaba con que "mantenimiento" y "oferta"
aparecieran sueltas.

Un párrafo de servicios —*"el adjudicatario será responsable del mantenimiento
preventivo de los equipos… La oferta económica deberá contemplar…"*— matcheaba
como garantías. Dos o tres falsos positivos así sobre un chunk corto alcanzan
para que la fórmula de densidad lo declare `primary_category` de una categoría
que no le corresponde.

**Fix aplicado** — los términos de una sola palabra siguen matcheando por token;
los de varias se buscan como **frase**, con bordes de palabra (el contenido
normalizado se rodea de espacios, así "oferta economica" no matchea dentro de
"ofertante economico"). Es estrictamente más preciso y más barato que el
subconjunto.

Cubierto por `backend/tests/test_clasificacion_de_chunks.py` (cuatro fallan al
revertir). Suite: 561 passed / 7 failed (los 7 de base).

Este fix **no necesitaba** el set de chunks etiquetados que había pedido: es una
corrección de precisión, no una calibración. Lo agrupé mal con CHK-08 al armar
el índice de estado.

---

### CHK-08 · media · Diagnóstico corregido: uno de los dos problemas no era lo que decía

**Estado: parcialmente resuelto (2026-08-14). La calibración sigue pendiente y necesita datos.**

Al ir a implementarlo, sólo uno de los dos problemas reportados era lo que el
hallazgo decía.

**Problema 1 — el comentario miente. Cierto, y el equivocado es el comentario.**
Decía "normalizado por cada 100 palabras para evitar penalizar chunks largos",
pero la fórmula es *inversamente* proporcional a la longitud. Sólo que eso está
bien: un término que aparece una vez en 700 palabras SÍ es menos indicativo que
uno que aparece una vez en 100 — densidad significa exactamente eso. Se corrige
el comentario, no la fórmula.

**Problema 2 — el piso `max(content_length / 100.0, 1.0)` NO era la causa. Es un
no-op.** Verificado por enumeración sobre `content_length` de 1 a 1500 y
`match_count` de 1 a 20: **cero** combinaciones donde el piso cambie el
resultado. Para `content_length < 100` el cociente ya es ≥ 1 y el
`min(..., 1.0)` posterior lo recorta igual.

El efecto reportado sí es real —un chunk de menos de 100 palabras con un solo
match llega a `(1/4) × 1.0 = 0.25`, exactamente `_DEFAULT_PRIMARY_THRESHOLD`—
pero la causa es otra: el **punto de saturación** de la densidad está
implícitamente en *un match cada 100 palabras*. Con esa unidad, cualquier chunk
corto es máximamente denso por definición.

Mi primer intento de fix fue reemplazar el piso por uno sobre la longitud
(`max(content_length, 60)`). Lo verifiqué antes de entregarlo y era **otro
no-op**, por la misma razón. Vale anotarlo: es la clase de cambio que se ve
razonable, pasa los tests y no hace nada.

**Qué se hizo** — corregir el comentario, y **sacar la calibración de la
penumbra**: el punto de saturación pasa a ser
`_DENSITY_SATURATION_PER_100_WORDS`, una constante con nombre, en vez de estar
escondido en la unidad de una división. El valor actual se conserva y el
comportamiento es **idéntico** (verificado por enumeración contra la fórmula
anterior: cero diferencias).

**Qué queda** — subir ese número cambia qué chunks pasan el umbral. Eso es
calibración, no un arreglo, y sin el set de chunks etiquetados no hay forma de
saber si mejora o empeora. Ahora hay un solo lugar donde tocarlo, y un test que
fija el comportamiento actual para que el día que se calibre se vea exactamente
qué cambió.

**Qué set hace falta, concretamente** — no etiquetar cientos de chunks:

1. la salida de `/api/debug/chunks/{id}?metadata_only=true&limit=500` sobre dos
   o tres pliegos ya analizados. Con eso se mide el síntoma sin etiquetas: qué
   proporción de chunks recibe `primary_category`, cuántos de ésos tienen menos
   de 100 palabras (la firma exacta de la saturación) y cuántas filas de tabla
   quedan clasificadas. El pliego `pliego_04_sin_garantias.pdf` vale doble: es
   el caso negativo, así que cualquier chunk clasificado como `garantias` ahí es
   un falso positivo confirmado sin que nadie tenga que opinar;
2. sobre los 30-40 casos que salgan sospechosos, cuál era la categoría correcta.
   Eso es el set.

---

### CHK-09 · media · La fusión de encabezados partidos concatenaba siempre sin espacio

**Estado: corregido (2026-08-14).**

`extraction/chunking.py::_join_split_heading`

Para el caso que motivó la función —`"ARTÍCULO 12: PLA"` + `"ZO DE ENTREGA"`—
concatenar sin espacio es correcto: Document Intelligence partió una **palabra**.
Pero el disparador `next_starts_lowercase` se activa también cuando lo que DI
partió es un **título en dos renglones tipográficos**, que es frecuente: página
N `"5. GARANTÍAS"`, página N+1 `"de cumplimiento de contrato"`. El resultado era
`"5. GARANTÍASde cumplimiento de contrato"`.

El token "garantiasde" no existe en ningún lado. `_classify_by_heading` lo
sobrevive de casualidad —busca "garantia" por substring y sigue siendo prefijo—
pero el `title` que va al embedding y al campo `searchable` del índice queda
corrupto. O sea: el chunk pierde capacidad de ser recuperado por el texto de su
propio título, que es exactamente lo que IDX-01 vino a garantizar.

**Fix aplicado** — se une **sin espacio sólo si se partió una palabra**, y con
espacio en todo otro caso. La distinción se hace por la forma de los tokens del
borde:

- hay letras a los dos lados del corte (si la izquierda termina en `:` o en un
  dígito, no se partió ninguna palabra);
- al menos uno de los dos tokens del borde parece un **pedazo**: una tirada
  corta en mayúsculas (`"PLA"`, `"ZO"`, `"ANTÍA"`) o, del lado derecho, una
  continuación en minúscula (`"tación"`);
- y la izquierda **no** termina en una palabra corta y completa. Es lo que
  separa `"3.1. Plataforma de"` + `"software…"` (título cortado, va espacio) de
  `"ARTÍCULO 6: DOCUMEN"` + `"tación…"` (palabra cortada, va pegado).

La lista de palabras cortas completas es inevitable —el hallazgo ya lo
anticipaba— y el archivo ya tenía una equivalente para `next_starts_with_article`.

**Segundo intento, otra vez.** La primera versión miraba sólo el largo del token
izquierdo (≤5 caracteres) y trataba `"DOCUMEN"` + `"tación"` como título en dos
renglones, produciendo `"DOCUMEN tación"`. **Lo atrapó un test que ya existía**
(`tests/extraction/test_merge_split_headings.py`), no uno mío: mis nueve casos
de prueba no incluían un pedazo izquierdo largo. Es el mismo patrón que ya
apareció con CHK-08: un fix que se ve razonable y falla en el caso que no se me
ocurrió. La suite completa entre cada cambio es lo que lo sostiene.

Cubierto por `backend/tests/test_encabezados_partidos_entre_paginas.py`
(14 tests, ocho de ellos guardas). Suite: 575 passed / 7 failed (los 7 de base).

Con esto **el grupo de clasificación de chunks queda cerrado**, salvo la
calibración de umbrales de CHK-08, que sigue esperando datos.

---

## Apéndice III · Verificación sobre el reanálisis (2026-08-14)

Los dos pliegos se reanalizaron con los fixes puestos y se miraron los chunks
completos (`metadata_only=true&limit=500`), no la vista por defecto:

- Bancor (PET), análisis `bbdc6bd5-b96d-4b80-8aa9-d13b1639ada3` — 111 chunks.
- Rosario, análisis `6b9c8af8-beb1-4b9a-b6f2-e971fe367484` — 30 chunks.

**Lo que quedó confirmado sobre datos reales**, no sobre fixtures:

| Fix | Evidencia en el reanálisis |
|---|---|
| ING-09 | Hay bbox en prácticamente todo bloque de párrafo de los dos documentos, y `para_id` son índices reales de DI (`[15, 206]`, `[39, 23]`), no posiciones inventadas. |
| CHK-13 | El índice de las páginas 2-3 del PET desapareció: el chunk 2 es de la página 2 y el 3 salta a la 4. |
| CHK-14 | Los 953 caracteres del chunk 12 ya no se repiten: el chunk 13 abre con los 108 caracteres del título solo. |
| CHK-16 | `section_path` del chunk 9 es `… > 1. Generalidades > 1.7. Plazo de entrega` (antes colgaba de `1.6.`), y el del 19 `… > 3.1. Plataforma … > 3.1.2. Virtualización`. |
| DBG-01 | `total_chunks: 111, returned_chunks: 20, truncated: true`. El endpoint ya no reporta una página como si fuera el total — que es justo lo que me hizo perseguir un falso positivo la primera vez. |

Y **destapó un hallazgo severo que ningún fixture podía mostrar**, más dos
residuos. Van abajo.

---

### CHK-17 · alta · Los encabezados de más de seis almohadillas se perdían enteros

`extraction/document_intelligence.py:29`

```python
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
```

El tope de seis es la regla de CommonMark. Document Intelligence **no emite
CommonMark**: cuando la jerarquía visual del documento pasa de seis niveles,
sigue agregando almohadillas. Comprobado línea por línea sobre el markdown del
PET:

```
HEADING nivel 1 | # PLIEGO DE ESPECIFICACIONES TÉCNICAS
HEADING nivel 6 | ###### 3.1.10. Herramientas
NO ES HEADING -> queda como párrafo | ####### 3.3. Equipamiento de cómputo y dimensionamiento (siz
NO ES HEADING -> queda como párrafo | ######## 3.3.1. Capacidades a satisfacer y base de cálculo
NO ES HEADING -> queda como párrafo | ######## EQUIPAMIENTO CÓMPUTO - NODOS TIPO SERVIDOR POR CADA
```

Esas líneas caían al acumulador de párrafos. Dos consecuencias, las dos visibles
en los chunks que reanalizamos:

1. **Las almohadillas quedaban literales dentro del texto del chunk.** El
   contenido del chunk 68 termina con `####### 3.3. Equipamiento de cómputo y
   dimensionamiento (sizing)`, y el del 69 contiene `######## 3.3.1. …` y
   `######## 3.3.2. …`. Eso va al embedding y al campo `searchable` del índice.

2. **La sección dejaba de existir como ancestro** — esto es lo caro. Todo lo que
   colgaba de 3.3 se enganchaba del último encabezado que sí había sido
   reconocido. Los chunks 64-72, que son contenido de 3.3, salieron con:

   ```
   PLIEGO … > · Equipo Principal de Almacenamiento de BackUp
            > o Rendimiento y Conectividad Mínima:
            > o Seguridad
            > 2.3.3) ITEM 3: EQUIPO DE ALMACENAMIENTO DE BACKUP SECUNDARIO
            > · Requerimiento de Capacidades
   ```

   Otra sección entera. El chunk 34 es `PLIEGO DE ESPECIFICACIONES TÉCNICAS >
   Capa de infraestructura y virtualización (VCF)`: perdió `3.`, `3.1.` y
   `3.1.8.` como ancestros. Los chunks 43 y 46 cuelgan `3.1.9.` y `3.2.` de
   `Resiliencia y backup seguro`. **De la página ~16 a la ~33 el `section_path`
   estaba mal.** Ese path alimenta el `section_hint` que desambigua el resaltado
   y el contexto que ve el redactor de la síntesis: la jerarquía inventada se
   propaga a las dos puntas.

Vale la pena decir por qué no apareció antes: **ningún test podía verlo**. Los
tests de headings del repo usan `#`, `##`, `###` — nadie escribe siete
almohadillas a mano en un fixture. Sólo aparece en un documento real con más de
seis niveles de jerarquía visual, y el pliego de Rosario no los tiene.

**Fix aplicado** — `^(#+)\s+(.+)$`, sin tope.

Se conserva la **profundidad real** en vez de recortarla a 6. Recortar dejaría
`3.3.` y `3.3.1.` en el mismo nivel, o sea hermanos para `pop_to_level`, y
`_normalize_decimal_heading_levels` (CHK-16) sólo puede reparar lo que está
numerado: `######## EQUIPAMIENTO CÓMPUTO - NODOS TIPO SERVIDOR` no lo está.

Lo que sigue sin ser encabezado, verificado como guarda: una línea de puras
almohadillas (no hay texto después del espacio), `#3 de la serie` y
`#######3.3.` (sin espacio), y el texto en mayúsculas o negrita sin almohadillas.

Cubierto por `backend/tests/test_encabezados_de_mas_de_seis_niveles.py`
(13 tests). Revirtiendo el regex fallan 8 de los 13. Suite: 588 passed /
7 failed (los 7 de base).

---

### CHK-18 · alta · Encabezado y cuerpo compiten por el mismo párrafo de DI

Destapado por el propio ING-09. Con el matching por texto, un encabezado y el
párrafo que le sigue pueden reclamar el mismo `paragraph` de Document
Intelligence, y uno de los dos queda sin bbox. Es exactamente el par que
`_starts_on_same_line` / CHK-12 necesita para decidir si un título cortado
continúa en la línea siguiente.

Efecto medido: en Rosario **los chunks 12 y 14 siguen partidos** —
`Artículo Nº 10: GAR` / `ANTÍA DE ADJUDICACIÓN…` y `ARTÍCULO 12: PLA` /
`ZO DE ENTREGA`. `_join_split_heading` sabe unirlos (CHK-09 lo cubre con tests);
lo que falta es que le lleguen con bbox para que la heurística se dispare.

Pendiente. Es el próximo fix natural.

### CHK-15 residual · media · Membretes que DI marca como encabezado

Los chunks 0 y 2 de Bancor siguen siendo membrete puro. El contador de
`_drop_repeated_page_furniture` sólo mira bloques de párrafo, así que un membrete
que DI marca como *heading* en la mayoría de las páginas nunca llega al 60%
contándolo como párrafo. El filtro funciona; le falta contar las dos formas.

### CHK-08 · calibración

Sin cambios: sigue esperando el set etiquetado. La perilla ya está aislada y con
nombre (`_DENSITY_SATURATION_PER_100_WORDS`).

---

### CHK-19 · alta · Un encabezado sin numerar se llevaba puesta toda la jerarquía

`extraction/chunking.py::_to_intermediate_blocks`

**CHK-17 quedó confirmado** en el reanálisis `476a0353` (113 chunks): los
encabezados de siete y ocho almohadillas son ahora encabezados de verdad — el
chunk 69 es `3.3. Equipamiento de cómputo y dimensionamiento (sizing)`, el 70 es
`3.3.1.`, el 71 es `3.3.2.` — y no quedó ni una almohadilla literal dentro del
texto de ningún chunk.

Pero el `section_path` de esa zona **seguía mal**, por una causa distinta que
sólo se pudo ver una vez que la primera estaba corregida:

```
chunk 34 | PLIEGO DE ESPECIFICACIONES TÉCNICAS > Capa de infraestructura y virtualización (VCF)
         ^ perdió 3., 3.1. y 3.1.8.

chunk 69 | PLIEGO … > · Equipo Principal de Almacenamiento de BackUp
           > 3.3. Equipamiento de cómputo y dimensionamiento (sizing)
         ^ la sección 3.3 colgada de una subsección de 3.2
```

Con CHK-16 puesto, los encabezados **numerados** quedan en el nivel que declara
su numeración. Los **no numerados** siguen en el que les asignó Azure DI, que lo
deduce de la tipografía. Las subsecciones en viñeta de 3.1.8 —`Capa de
infraestructura y virtualización (VCF)`, `Resiliencia y backup seguro`, `·
Equipo Principal de Almacenamiento de BackUp`— salieron en **nivel 2**, el mismo
que `3. Especificaciones técnicas`. Y un encabezado de nivel 2 hace
`pop_to_level(2)`: se lleva puestos a `3.`, `3.1.` y `3.1.8.` de una sola vez.
Después `3.3.`, que por su numeración es nivel 3, ya no puede desalojar a la
viñeta de nivel 2 y termina colgando de ella.

**Fix aplicado** — la regla es: *si el pliego hubiera querido que ese título
fuera hermano de las secciones numeradas, lo habría numerado*. Cada tramo de
encabezados sin numerar se desplaza en bloque para quedar por debajo del último
numerado.

Se **desplaza**, no se aplasta contra el piso: aplastar convertiría en hermanos
a encabezados que DI puso uno dentro del otro. Lo que DI haya dicho sobre la
jerarquía *relativa* entre ellos se conserva intacto; lo único que se corrige es
dónde se engancha el tramo entero.

Guardas verificadas:

- **Un pliego sin numeración decimal no se toca.** El de Rosario numera por
  `Artículo Nº 10:`, que no declara profundidad: sin encabezados numerados no
  hay piso y la función no tiene nada que opinar. Sale por la primera línea.
- **Los encabezados previos al primer numerado no se tocan** — la carátula es
  ancestro de todo, no descendiente de nada.
- **Un anexo sigue siendo hermano de las secciones.** Es la única excepción
  conocida a la regla, y está sostenida por el dominio: un pliego que numera sus
  secciones igual pone `ANEXO I` al mismo nivel. Además, un anexo corta el tramo
  pero **no fija piso**: su propio nivel lo sigue poniendo DI, así que usarlo
  como piso propagaría justo el error que se está corrigiendo.

Corre al final del pipeline de encabezados, después de
`_promote_run_in_headings` —que emite encabezados con nivel 2 fijo, o sea
exactamente el nivel que rompe la jerarquía numerada.

Cubierto por `backend/tests/test_secciones_sin_numerar.py` (13 tests, siete de
ellos guardas). Revirtiendo el enganche en el pipeline fallan los 4 tests de
integración. Suite: 601 passed / 7 failed (los 7 de base).

---

## Apéndice IV · Verificación de CHK-19 (2026-08-14)

Reanálisis `7bce4799-a2bf-4407-9184-4b68c9687443`, 113 chunks. **La jerarquía
quedó bien de punta a punta del documento.** Los cinco lugares que estaban rotos:

| chunk | antes | ahora |
|---|---|---|
| 34 | `PLIEGO > Capa de infraestructura y virtualización (VCF)` | `PLIEGO > 3. > 3.1. > 3.1.8. > Capa de infraestructura y virtualización (VCF)` |
| 43 | `PLIEGO > Resiliencia y backup seguro > 3.1.9.` | `PLIEGO > 3. > 3.1. > 3.1.9.` |
| 46 | `PLIEGO > Resiliencia y backup seguro > 3.2.` | `PLIEGO > 3. > 3.2.` |
| **69** | `PLIEGO > · Equipo Principal de Almacenamiento de BackUp > 3.3.` | `PLIEGO > 3. > 3.3.` |
| 85, 90 | `… > 4. Servicios … > Almacenamiento secundario de respaldo` (4.5 desalojado) | `… > 4.5. Servicio de administración … > Almacenamiento secundario de respaldo` |

Y las guardas se sostuvieron sobre datos reales: la carátula sigue siendo
ancestro de todo (chunks 1-2), y **`9. Anexos` no quedó enterrado** — sale como
`PLIEGO DE ESPECIFICACIONES TÉCNICAS > 9. Anexos`, hermano del resto.

### Residuos que quedan a la vista

**R1 · La jerarquía *relativa* entre encabezados sin numerar sigue siendo la que
adivinó DI.** Los chunks 64-68 llevan
`… > 3.2. … > · Equipo Principal … > o Rendimiento y Conectividad Mínima: > o
Seguridad > 2.3.3) ITEM 3: … > · Requerimiento de Capacidades`. `o Rendimiento`
y `o Seguridad` son hermanos —misma viñeta, misma sangría—, no padre e hijo.
CHK-19 lo conserva **a propósito**: desplaza el tramo, no lo aplasta. Lo que sí
cambió es que ahora todo eso cuelga de `3.2.`, que es la sección correcta.

Adentro de ese residuo hay un caso separable: **`2.3.3) ITEM 3: EQUIPO DE
ALMACENAMIENTO DE BACKUP SECUNDARIO` sí está numerado**, sólo que cierra con
paréntesis en vez de punto, y `_DECIMAL_HEADING_RE` exige el punto final. Un
pliego que numera `2.3.3)` declara profundidad igual que uno que numera
`2.3.3.`. Antes de tocarlo hay que mirar que en ESTE documento ese encabezado es
un resto de otro pliego (la numeración propia es `3.x`), así que reconocerlo lo
colgaría de un `2.` que acá no existe. **No implementado: necesita mirar un
segundo pliego con numeración de paréntesis antes de decidir.**

**R2 · Un bloque de párrafo recibió el bbox de una celda de tabla.** El chunk 95
—192 caracteres, `· El adjudicatario deberá tener capacidad de brindar soporte
presencial (on-site)…`— tiene un único bbox de **84,4 × 30,9 pt**, byte por byte
el mismo rectángulo que la celda `col_3: Tiempo de respuesta` del encabezado de
la tabla del chunk 94. Los demás párrafos de esa página miden ~450 pt de ancho:
en 84 pt de ancho por 31 de alto no entran 192 caracteres. O sea, el resaltado de
esa cita caería sobre una celda de la tabla, no sobre el texto citado.
Es del mismo grupo que CHK-18 (bloque y párrafo de DI compitiendo), y hay que
mirarlo con el `result.paragraphs` crudo delante antes de proponer nada.

**R3 · Un chunk de un solo carácter.** El chunk 24 es `•` — la viñeta suelta que
DI dejó bajo `3.1.7. Conectividad de Red`. `content_length: 1`. No aporta nada al
índice y ocupa una posición de retrieval.

**CHK-18 sigue pendiente** y es el próximo fix natural: los chunks 12 y 14 de
Rosario siguen partidos (`Artículo Nº 10: GAR` / `ANTÍA DE ADJUDICACIÓN…`).

---

### ING-10 · alta · Un párrafo se quedaba con el bbox de una celda de tabla

`extraction/document_intelligence.py::_same_text`

```python
if izquierda in derecha or derecha in izquierda:
    return True
```

La contención se aceptaba **en cualquier posición**. Un párrafo corto se mete por
casualidad en el medio de cualquier párrafo largo que mencione las mismas
palabras — y `result.paragraphs` de Document Intelligence incluye las **celdas de
las tablas**, que son justamente textos cortos. El guard que existía
(`_PARA_MATCH_EXACT_BELOW_CHARS = 8`) sólo protege textos de menos de ocho
caracteres.

**Evidencia, del reanálisis `7bce4799` (R2 del apéndice anterior).** El chunk 95:

```
contenido | "· El adjudicatario deberá tener capacidad de brindar soporte
             presencial (on-site) cuando la severidad lo requiera o el Banco lo
             solicite, con un tiempo de respuesta on-site no mayor a 3 horas."
bbox      | x 390,3  y 504,6  w 84,4  h 30,9
```

Ese rectángulo es, byte por byte, el de la celda `col_3: Tiempo de respuesta`
del encabezado de la tabla del chunk 94. En 84 pt de ancho por 31 de alto no
entran 192 caracteres — los demás párrafos de esa página miden ~450 pt. Y la
causa está a la vista en el texto: **`"tiempo de respuesta"` aparece adentro del
párrafo**, en el medio. El resaltado de esa cita caía sobre una celda de la
tabla.

**Fix aplicado** — la contención tiene que estar **anclada a un borde**:

```python
izquierda.startswith(derecha) or izquierda.endswith(derecha)
or derecha.startswith(izquierda) or derecha.endswith(izquierda)
```

Un fragmento de verdad empieza donde empieza el otro texto o termina donde
termina: el parser corta el párrafo de DI por el principio (`"Artículo Nº 10:
GAR"` es prefijo de la línea entera, que es el caso de CHK-12) o le saca una
viñeta del principio (el párrafo de DI queda como sufijo del bloque). En el medio
no hay ninguna relación estructural — sólo vocabulario compartido, que es
exactamente lo que este emparejamiento **no** tiene que usar: para eso están el
retrieval y el ranking, no el mapeo de coordenadas.

Se conservan las dos ramas que ya estaban: igualdad exacta por debajo de 8
caracteres (un índice es una página llena de números sueltos) y comparación de
los primeros 40 caracteres cuando los textos divergen al final.

Cubierto por `backend/tests/test_bbox_de_celda_de_tabla.py` (10 tests, cinco de
ellos guardas sobre fragmentos legítimos). Revirtiendo la condición fallan 2.
Suite: 611 passed / 7 failed (los 7 de base).

**Lo que ING-10 NO arregla, y conviene decirlo:** CHK-18. Trabajando este fix
quedó clara la mecánica de aquel, y es otra. Si DI emite **un solo** párrafo para
la línea `"Artículo Nº 10: GARANTÍA DE ADJUDICACIÓN: En caso de corresponder…"`
y el markdown la parte en encabezado + cuerpo, entonces:

1. el encabezado `"Artículo Nº 10: GAR"` matchea ese párrafo por prefijo, lo toma
   y lo marca en `usados`;
2. el cuerpo `"ANTÍA DE ADJUDICACIÓN: En caso…"` encuentra el único párrafo que
   le corresponde ya ocupado → `bbox = []`;
3. `_starts_on_same_line` devuelve `False` por falta de bbox → **no se fusiona**.

O sea: que los dos bloques reclamen el mismo párrafo de DI no es el problema, es
**la prueba** de que DI partió una sola línea visual — evidencia más fuerte que
la comparación geométrica que hoy usa CHK-12. El fix natural es dejar que el
cuerpo herede el `para_id` del encabezado cuando la concatenación de los dos
reproduce el párrafo de DI. Antes de escribirlo quiero ver el `result.paragraphs`
crudo de esa página de Rosario: si DI emite dos párrafos y no uno, la mecánica es
otra y el fix también.

---

### CHK-18 · **descartado**: el mecanismo que propuse no ocurre

Corrida del diagnóstico sobre el pliego de Rosario (`Pliego Licitacion Privada
Servidores 2025(3).pdf`), con ING-10 puesto:

```
match_rate_pct=100.0  matched=126  no_match=0  text_mismatch=0
PASO 4 · bloques con bbox: 126 / 126  (100.0%)
PASO 5 · no fusionó nada · pares en la misma línea visual: ninguno
PASO 6 · ninguno: todos los cuerpos que siguen a un encabezado tienen bbox
```

**El PASO 6 lo mata.** Mi hipótesis era que el encabezado se quedaba con el único
párrafo de DI y el cuerpo terminaba sin bbox. No hay un solo caso: los 126
bloques tienen bbox. Así que ni implemento el fix que había esbozado ni lo dejo
como pendiente — no existe el problema que describía.

**Y lo que sí muestra la corrida es más incómodo:** el encabezado que dio origen
a toda esta línea de trabajo *no está cortado en esta corrida*. En el log de
PASO 3-4:

```
heading_detected  page=4  'ARTÍCULO 11: ORDEN DE PROVISIÓN'          source_order=57
potential_missed_heading  page=4  'ARTÍCULO 12: PLAZO DE ENTREGA'    source_order=60
                                                        uppercase_ratio=0.76
```

`ARTÍCULO 12: PLAZO DE ENTREGA` viene **entero** — no `ARTÍCULO 12: PLA` +
`ZO DE ENTREGA`. Y entre `ARTÍCULO 9: ADJUDICACIÓN` (orden 49) y `ARTÍCULO 11`
(orden 57) **no hay ningún encabezado de Artículo 10**, que es el de GARANTÍA DE
ADJUDICACIÓN.

O sea: **Document Intelligence devolvió una segmentación distinta para el mismo
PDF.** El corte que vimos en el análisis guardado `6b9c8af8` (chunks 12 y 14) no
se reproduce hoy. Eso cambia el método, no sólo este hallazgo:

- **CHK-12 se queda.** El corte pasa a veces; que no pase hoy no lo vuelve
  innecesario, lo vuelve *no reproducible a pedido*.
- **Un análisis guardado no es una reproducción estable.** Venía tratando los
  chunks de un análisis viejo como si fueran la salida determinística del
  pipeline sobre ese PDF, y no lo son. De acá en adelante, cualquier hallazgo que
  dependa de la segmentación de DI necesita la corrida del diagnóstico al lado,
  no sólo el JSON de chunks.

### CHK-21 · alta · Artículos que DI no marca como encabezado quedan invisibles

Lo que **sí** está roto hoy en Rosario, y es el mismo daño al usuario que
perseguía CHK-12 pero por otra puerta: `ARTÍCULO 12: PLAZO DE ENTREGA` y
`Artículo Nº 10: GARANTÍA DE ADJUDICACIÓN` no son encabezados. Consecuencia
directa:

- no abren sección, así que su `section_path` es el del artículo anterior;
- su texto no llega al campo `title` del chunk, que es lo que IDX-01 puso en el
  campo `searchable` del índice;
- para `plazos_clave` y `garantias`, el artículo que contiene la respuesta no se
  puede recuperar por el texto de su propio título.

El pipeline **ya sabe** que esto pasa: `_parse_markdown_blocks` calcula un
`uppercase_ratio` y emite `potential_missed_heading` — y no hace nada más que
loguearlo (`document_intelligence.py:722`). La señal está a medio construir desde
antes de esta auditoría.

Antes de promover nada hay que separar dos formas, porque el fix es distinto:

  (a) el título es un párrafo **corto y suelto** → alcanza con promoverlo;
  (b) el título viene **pegado a su cuerpo** en el mismo párrafo → hay que
      partir el bloque, que es mucho más delicado.

`ARTÍCULO 12: PLAZO DE ENTREGA` es (a) —29 caracteres, disparó el log—.
`Artículo Nº 10` no disparó el log, así que o supera los 100 caracteres o tiene
poca mayúscula: probablemente sea (b). **Agregado el PASO 7 al diagnóstico** para
medirlo sobre los dos pliegos antes de escribir una línea de fix. Promover por
`uppercase_ratio > 0.5` a ciegas convertiría en encabezado cualquier línea en
mayúsculas —`PRESUPUESTO OFICIAL: $ X`, `APERTURA:`, `ITEMS:` ya aparecen en el
log— y fabricar secciones falsas es tan malo como perderlas.
