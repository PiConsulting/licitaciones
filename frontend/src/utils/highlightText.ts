const MIN_MATCH_LENGTH = 3;

function normalizeText(value: string): string {
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
export function createCitationTextRenderer(citationTexts: string[]) {
  return ({ str }: { str: string }): string => {
    const escaped = escapeHtml(str);
    if (citationTexts.length === 0 || !isPartOfCitation(str, citationTexts)) {
      return escaped;
    }
    return `<mark style="background-color:#FEF3C7;color:inherit;border-radius:2px;">${escaped}</mark>`;
  };
}
