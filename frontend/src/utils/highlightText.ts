// Fallback de resaltado (capa de texto react-pdf) cuando el backend no calculó coordenadas; marca solo palabra completa contenida en la cita, sin buffer ni estado global (evita bug 2026-08-14 de resaltar párrafos enteros).

/** Mínimo de caracteres discriminantes; por debajo son preposiciones/artículos comunes a cualquier cita. */
const MIN_FRAGMENT_LENGTH = 4;

/** Palabras frecuentes en cualquier pliego; marcarlas no aporta señal. */
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

const CITATION_GAP_MARKER_RE = /\s*(?:\[\.\.\.\]|…)\s*/g;

export function normalizeText(value: string): string {
  const withoutTableMarkers = value.replace(/\bcol_\d+\s*:\s*/gi, " ");
  const withoutAccents = withoutTableMarkers
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
  return withoutAccents.replace(/\s+/g, " ").trim().toLowerCase();
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

  const normalizeCitationCandidates = (citationText: string): string[] => {
    const raw = citationText ?? "";
    const normalizedBase = normalizeText(raw);
    const candidates: string[] = [];
    if (normalizedBase) {
      candidates.push(normalizedBase);
    }

    if (raw.includes("[...]") || raw.includes("…")) {
      const parts = raw
        .split(CITATION_GAP_MARKER_RE)
        .map((part) => normalizeText(part))
        .filter((part) => part.length >= MIN_FRAGMENT_LENGTH)
        .sort((a, b) => b.length - a.length);
      for (const part of parts) {
        if (!candidates.includes(part)) {
          candidates.push(part);
        }
      }
    }

    return candidates;
  };

  return citationTexts.some((citationText) =>
    normalizeCitationCandidates(citationText).some(
      (candidate) =>
        // Caso normal: span dentro de la cita.
        containsAsWord(candidate, fragment) ||
        // Fallback robusto: cita recortada dentro de un span mayor.
        (candidate.length >= MIN_FRAGMENT_LENGTH && containsAsWord(fragment, candidate)),
    ),
  );
}

// Semitransparente para no tapar el texto del canvas; box-decoration-break:clone une los spans de una misma línea en un solo bloque.
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
