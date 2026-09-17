const CURRENCY_TITLE = "Licitación en pesos o dólares";
const GARANTIAS_TITLE = "Garantías o cauciones";

const PERCENT_PATTERN = /\d+(?:[.,]\d+)?\s?%/g;

function normalizeCurrency(source: string): string | null {
  const value = source.toLowerCase();
  const hasUSD = /d[oó]lar|usd/.test(value);
  const hasARS = /peso|\bars\b/.test(value);
  if (hasUSD && hasARS) {
    return "ARS / USD";
  }
  if (hasUSD) {
    return "USD";
  }
  if (hasARS) {
    return "ARS";
  }
  return null;
}

const GARANTIA_LABELS: Array<{ match: RegExp; label: string }> = [
  { match: /oferta/i, label: "Oferta" },
  { match: /cumplimiento|contrato/i, label: "Cumplimiento" },
  { match: /anticipo/i, label: "Anticipo" },
  { match: /impugnaci/i, label: "Impugnación" },
  { match: /adicional/i, label: "Adicional" },
];

function shortGarantiaLabel(segment: string): string | null {
  return GARANTIA_LABELS.find(({ match }) => match.test(segment))?.label ?? null;
}

function normalizeGarantias(detailText: string): string | null {
  const clean = (value: string) => value.replace(/\s+/g, "");
  const matches = detailText.match(PERCENT_PATTERN);
  if (!matches || matches.length === 0) {
    return null;
  }
  if (matches.length === 1) {
    return clean(matches[0]);
  }

  // Varias garantías en el mismo texto: un título corto (si se reconoce el
  // tipo) más su porcentaje, por cada una -- no un solo % suelto que no
  // distinga a cuál corresponde.
  const segments = detailText.split(/[,;]|\by\b/i);
  const parts: string[] = [];
  for (const segment of segments) {
    const segmentMatches = segment.match(PERCENT_PATTERN);
    if (!segmentMatches) {
      continue;
    }
    const percent = clean(segmentMatches[segmentMatches.length - 1]);
    const label = shortGarantiaLabel(segment);
    parts.push(label ? `${label} ${percent}` : percent);
  }
  return parts.length > 0 ? parts.join(" · ") : matches.map(clean).join(" · ");
}

/**
 * Ajustes puntuales de visualización para dos criterios del preview: moneda
 * se normaliza a código (ARS/USD) y garantías muestra el/los porcentaje/s en
 * vez de la frase libre del LLM. Solo afecta el resumen de la card colapsada
 * -- el detalle expandido sigue mostrando el texto original del análisis sin
 * modificar.
 */
export function normalizePreviewSummary(
  title: string,
  resumen: string | undefined,
  detailText: string,
): string | undefined {
  if (!resumen || resumen === "No informado" || resumen === "No especificado") {
    return resumen;
  }

  if (title === CURRENCY_TITLE) {
    return normalizeCurrency(`${resumen} ${detailText}`) ?? resumen;
  }

  if (title === GARANTIAS_TITLE) {
    return normalizeGarantias(detailText) ?? resumen;
  }

  return resumen;
}
