const MIN_MATCH_LENGTH = 3;

export function normalizeText(value: string): string {
  return value.replace(/\s+/g, " ").trim().toLowerCase();
}

function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** True when a PDF text-layer item is (approximately) part of one of the given citations. */
export function isPartOfCitation(itemText: string, citationTexts: string[]): boolean {
  const normalizedItem = normalizeText(itemText);
  if (normalizedItem.length < MIN_MATCH_LENGTH) {
    return false;
  }
  return citationTexts.some((citationText) => normalizeText(citationText).includes(normalizedItem));
}

/**
 * Builds a react-pdf `customTextRenderer`: for each text item rendered on the page,
 * wraps it in a `<mark>` when it's part of one of `citationTexts`. This highlights the
 * real, rendered text directly (via react-pdf's own text layer), so it stays correctly
 * positioned at any zoom/fit level instead of relying on separately-computed pixel
 * coordinates that drift out of sync when the page's render size changes.
 */
// Semitransparente (no opaco) para que el texto real, renderizado en el canvas
// de abajo, se siga leyendo debajo de la marca — antes cubría el texto por
// completo. `box-decoration-break: clone` hace que los distintos spans del
// text layer que caen en una misma linea (react-pdf fragmenta el texto en
// varios spans) se vean como un unico bloque continuo de resaltador, en vez
// de "chips" opacos salteados con espacios entre palabras.
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
