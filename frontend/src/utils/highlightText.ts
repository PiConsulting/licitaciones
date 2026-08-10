// react-pdf/pdfjs fragmenta cada línea en muchos spans de texto (a veces una
// sola palabra). Para resaltar correctamente una frase completa, necesitamos
// reconstruir el texto de múltiples spans y buscar la cita como frase continua.
// Este algoritmo acumula spans hasta encontrar la frase completa o determinar
// que no está presente en esa secuencia.

// Buffer de contexto: cuántos spans consecutivos acumular para buscar la frase
const SPAN_CONTEXT_WINDOW = 20;

// Mínimo de longitud de palabra individual para considerar como parte de cita
const MIN_WORD_LENGTH = 8;

export function normalizeText(value: string): string {
  return value.replace(/\s+/g, " ").trim().toLowerCase();
}

function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/**
 * Determina si un span de texto es parte de alguna citation.
 * 
 * ESTRATEGIA MEJORADA:
 * 1. Si el span es largo (>= MIN_WORD_LENGTH), verificar si es palabra significativa de la cita
 * 2. Mantener un buffer global de spans recientes para detectar frases completas
 * 3. Solo marcar spans que sean parte de una frase verificable
 * 
 * NOTA: Esta función se llama span por span durante el render. Para mejorar
 * la precisión, react-pdf necesitaría exponer el texto completo de la página,
 * pero esa API no está disponible. Esta es la mejor aproximación dentro de
 * las limitaciones de la biblioteca.
 */

// Buffer global para acumular texto entre llamadas consecutivas
let spanBuffer: Array<{ text: string; normalized: string }> = [];
let lastResetTime = Date.now();

export function isPartOfCitation(itemText: string, citationTexts: string[]): boolean {
  // Reset buffer si pasó mucho tiempo (indica nueva página/render)
  if (Date.now() - lastResetTime > 1000) {
    spanBuffer = [];
  }
  lastResetTime = Date.now();

  const normalizedItem = normalizeText(itemText);
  if (!normalizedItem) {
    return false;
  }

  // Agregar span actual al buffer
  spanBuffer.push({ text: itemText, normalized: normalizedItem });
  if (spanBuffer.length > SPAN_CONTEXT_WINDOW) {
    spanBuffer.shift();
  }

  // Reconstruir texto del buffer
  const bufferedText = spanBuffer.map((s) => s.normalized).join(" ");

  // Estrategia 1: Buscar la frase completa en el buffer
  for (const citationText of citationTexts) {
    const normalizedCitation = normalizeText(citationText);
    
    // Si encontramos la frase completa (o gran parte) en el buffer, este span es parte
    if (bufferedText.includes(normalizedCitation)) {
      return true;
    }
    
    // Si la cita está contenida en el buffer con ligeras variaciones (75% match)
    const citationWords = normalizedCitation.split(" ").filter((w) => w.length >= 4);
    if (citationWords.length >= 3) {
      const matchedWords = citationWords.filter((word) => bufferedText.includes(word));
      if (matchedWords.length / citationWords.length >= 0.75) {
        return true;
      }
    }
  }

  // Estrategia 2: Si el span es una palabra larga significativa de la cita
  if (normalizedItem.length >= MIN_WORD_LENGTH) {
    for (const citationText of citationTexts) {
      const normalizedCitation = normalizeText(citationText);
      // Solo marcar si es palabra significativa (no común) Y aparece en la cita
      if (normalizedCitation.includes(normalizedItem)) {
        // Verificar que no sea una palabra demasiado común
        const commonWords = [
          "documento",
          "oferta",
          "oferente",
          "presentar",
          "garantia",
          "requisito",
          "vigente",
        ];
        if (!commonWords.includes(normalizedItem)) {
          return true;
        }
      }
    }
  }

  return false;
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
