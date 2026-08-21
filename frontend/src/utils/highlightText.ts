// Resaltado de respaldo, sobre la capa de texto de react-pdf.
//
// Este camino sólo corre cuando el backend NO pudo calcular coordenadas para la
// cita (ver `coordinateBasedHighlight.tsx` y `PDFPage.tsx`). Es una degradación
// deliberada: marca el texto que react-pdf ya posicionó, así que nunca queda
// desalineado, pero no puede recortar dentro de un span.
//
// FIX (2026-08-14): la versión anterior mantenía un BUFFER GLOBAL de los
// últimos 20 spans y devolvía `true` en cuanto el 75% de las palabras de la
// cita hubiera aparecido en ese buffer. Como todas las palabras de una cita
// están, por construcción, en el mismo párrafo, el buffer se llenaba mientras
// el párrafo se pintaba y a partir de ahí TODO span siguiente daba `true`.
// Sumado a que `createCitationTextRenderer` envuelve el span ENTERO, el
// resultado era el párrafo completo resaltado. Peor todavía: el buffer era de
// módulo y el visor renderiza hasta 5 páginas a la vez, así que se contaminaba
// entre páginas, y el reset era por tiempo (1 segundo), no por página.
//
// El contrato correcto -- el que los tests de este archivo ya describían -- es
// mucho más chico: un span se marca sólo si su texto está literalmente dentro
// de la cita, como palabra completa. Sin buffers, sin estado, sin porcentajes.

/** Mínimo de caracteres para que un fragmento sea discriminante. Por debajo de
 * esto son preposiciones y artículos que aparecen en cualquier cita. */
const MIN_FRAGMENT_LENGTH = 4;

/** Palabras de 4+ letras tan frecuentes en un pliego que marcarlas no señala
 * nada: aparecen en casi toda cita y en casi todo párrafo. */
const STOPWORDS = new Set([
  "para",
  "como",
  "esta",
  "este",
  "sobre",
  "entre",
  "desde",
  "hasta",
  "cuando",
  "donde",
  "porque",
  "pero",
  "sera",
  "seran",
  "deberá",
  "debera",
  "deberán",
  "deberan",
]);

export function normalizeText(value: string): string {
  return value.replace(/\s+/g, " ").trim().toLowerCase();
}

function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** ¿`fragment` aparece en `text` como palabra completa? Evita que "de" matchee
 * dentro de "deberán" y que "oferta" matchee dentro de "ofertante". */
function containsAsWord(text: string, fragment: string): boolean {
  let from = 0;
  for (;;) {
    const index = text.indexOf(fragment, from);
    if (index === -1) {
      return false;
    }
    const before = index === 0 ? " " : text[index - 1];
    const afterIndex = index + fragment.length;
    const after = afterIndex >= text.length ? " " : text[afterIndex];
    const isWordChar = (ch: string) => /[\p{L}\p{N}]/u.test(ch);
    if (!isWordChar(before) && !isWordChar(after)) {
      return true;
    }
    from = index + 1;
  }
}

/**
 * Determina si un span de la capa de texto forma parte de alguna cita.
 *
 * Criterio único: el texto del span tiene que estar CONTENIDO en la cita, como
 * palabra completa, y ser lo bastante largo como para discriminar. Nada de
 * coincidencias parciales ni acumuladas — marcar de más es peor que no marcar,
 * porque le dice a la persona que la evidencia es más grande de lo que es.
 */
export function isPartOfCitation(itemText: string, citationTexts: string[]): boolean {
  const fragment = normalizeText(itemText);
  if (fragment.length < MIN_FRAGMENT_LENGTH || STOPWORDS.has(fragment)) {
    return false;
  }

  return citationTexts.some((citationText) =>
    containsAsWord(normalizeText(citationText), fragment),
  );
}

// Semitransparente (no opaco) para que el texto real, renderizado en el canvas
// de abajo, se siga leyendo debajo de la marca. `box-decoration-break: clone`
// hace que los distintos spans del text layer que caen en una misma línea se
// vean como un único bloque continuo de resaltador, en vez de "chips" opacos
// salteados con espacios entre palabras.
const HIGHLIGHT_STYLE =
  "background-color:rgba(250,204,21,0.35);color:inherit;padding:0.05em 0;" +
  "box-decoration-break:clone;-webkit-box-decoration-break:clone;";

export function createCitationTextRenderer(citationTexts: string[]) {
  return ({ str }: { str: string }): string => {
    const escaped = escapeHtml(str);
    if (citationTexts.length === 0 || !isPartOfCitation(str, citationTexts)) {
      return escaped;
    }
    return `<mark style="${HIGHLIGHT_STYLE}">${escaped}</mark>`;
  };
}
