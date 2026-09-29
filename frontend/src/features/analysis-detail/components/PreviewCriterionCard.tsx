import { Eye } from "lucide-react";

import type { Citation, NarrativeBulletItem, NarrativeSource } from "../types";
import { sourceToCitation } from "../utils/resolveNarrativeSources";
import { splitLabelAndValue } from "../utils/splitLabelAndValue";

interface PreviewCriterionCardProps {
  title: string;
  resumen: string | undefined;
  bulletItem: NarrativeBulletItem;
  sources: NarrativeSource[];
  onViewSource?: (payload: { citation: Citation; citations: Citation[]; sources: NarrativeSource[] }) => void;
}

export function PreviewCriterionCard({
  title,
  resumen,
  bulletItem,
  sources,
  onViewSource,
}: PreviewCriterionCardProps) {
  const safeResumen = resumen ?? "—";
  const normalizedSafeResumen = safeResumen.trim();
  const detailText = splitLabelAndValue(bulletItem.text)?.value ?? bulletItem.text;
  const normalizedSummary = safeResumen.trim().toLowerCase();
  const normalizedDetail = detailText.trim().toLowerCase();
  const isMissing =
    normalizedSummary === "no informado" ||
    normalizedSummary === "—" ||
    normalizedSummary === "-" ||
    normalizedDetail.includes("no se encontró información") ||
    normalizedDetail.includes("no se encontro informacion");
  // `conflict_count` es estructurado (viaja desde merge_node, no depende de que el
  // LLM de síntesis escriba la palabra "conflicto"). El text-sniffing queda solo
  // como fallback para narrativas ya persistidas antes de este campo -- se pierde
  // al reanalizar, no hace falta migrar datos viejos.
  const conflictCount = bulletItem.conflict_count ?? 0;
  const hasTextualConflictHint = normalizedDetail.includes("conflicto") || normalizedSummary.includes("conflicto");
  const isWarn = !isMissing && (conflictCount > 0 || hasTextualConflictHint);
  // Algunos criterios arman `detailText` con un salto de línea por hecho real (ver `_project_multas_penalidades`); se muestran juntos en una sola línea, recortada, para no variar la altura de la card.
  const detailLines = detailText.split("\n").filter((line) => line.trim().length > 0);
  const detailSummaryText = detailLines.join(" · ");
  const summarySize = normalizedSafeResumen.length > 7 ? "text-[22px]" : "text-[30px]";
  const statusDotClass = isMissing ? "bg-[rgba(0,60,107,.25)]" : isWarn ? "bg-[#A966FF]" : "bg-[#1FC9A8]";
  const cardClass = isMissing
    ? "border-[rgba(0,60,107,.12)] bg-[#F4F9FC]"
    : isWarn
      ? "border-[rgba(169,102,255,.5)] bg-white"
      : "border-[rgba(0,60,107,.12)] bg-white";
  const summaryClass = isMissing ? "cedi-preview-card-value-muted" : "";
  const metaText = isMissing
    ? "No encontrado"
    : isWarn
      ? conflictCount > 0
        ? `${conflictCount} conflicto${conflictCount === 1 ? "" : "s"}`
        : "A revisar"
      : "Encontrado";
  const metaClass = isMissing
    ? "text-[rgba(0,60,107,.55)]"
    : isWarn
      ? "text-[#6E2FC9]"
      : "text-[#0B6B58]";

  const handleViewSource = () => {
    if (!onViewSource || sources.length === 0) {
      return;
    }
    const citations = sources.map(sourceToCitation);
    onViewSource({ citation: citations[0], citations, sources });
  };

  const summaryParts = (() => {
    if (isMissing) {
      return { big: "—", unit: "sin información" };
    }

    const percentMatches = normalizedSafeResumen.match(/\d+(?:[.,]\d+)?\s?%/g);
    if (percentMatches && percentMatches.length >= 2) {
      const big = percentMatches.map((p) => p.replace(/\s+/g, "")).join(" · ");
      const unitTokens = normalizedSafeResumen
        .replace(/\d+(?:[.,]\d+)?\s?%/g, "")
        .split("·")
        .map((t) => t.trim())
        .filter((t) => t.length > 0)
        .join(" · ");
      return { big, unit: unitTokens || "" };
    }

    // Para moneda compuesta (ej. ARS / USD) mantener ambos códigos en el
    // valor principal, así se renderizan con el mismo tamaño tipográfico.
    if (/^[A-Za-z]{3}\s*\/\s*[A-Za-z]{3}$/.test(normalizedSafeResumen)) {
      return { big: normalizedSafeResumen.toUpperCase().replace(/\s*\/\s*/, " / "), unit: "" };
    }

    if (/^a cargo del?\s/i.test(normalizedSafeResumen)) {
      return { big: normalizedSafeResumen, unit: "" };
    }

    const firstSpace = normalizedSafeResumen.indexOf(" ");
    if (firstSpace <= 0) {
      return { big: normalizedSafeResumen, unit: "" };
    }

    return {
      big: normalizedSafeResumen.slice(0, firstSpace),
      unit: normalizedSafeResumen.slice(firstSpace + 1),
    };
  })();

  return (
    <article
      className={`relative flex min-h-[132px] flex-col gap-[10px] overflow-hidden rounded-2xl border px-[18px] py-4 text-left transition-all ${cardClass}`}
      data-testid="preview-criterion-card"
    >
      <div className="flex items-start justify-between gap-2">
        <h4
          className="cedi-preview-card-title line-clamp-2"
          data-testid="preview-criterion-title"
        >
          {title}
        </h4>
        <span className={`mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full ${statusDotClass}`} aria-hidden="true" />
      </div>

      <div className="flex flex-1 flex-col justify-center gap-[6px]">
        <div className="flex items-baseline flex-wrap gap-x-2 gap-y-1" data-testid="preview-criterion-summary">
          <span className={`cedi-preview-card-value break-words ${summarySize} ${summaryClass}`} data-testid="preview-criterion-value">
            {isMissing ? <span className="italic">{summaryParts.big}</span> : summaryParts.big}
          </span>
          {summaryParts.unit ? (
            <span className="cedi-preview-card-unit" data-testid="preview-criterion-unit">
              {summaryParts.unit}
            </span>
          ) : null}
        </div>
        <p
          className="cedi-preview-card-detail line-clamp-2 break-words"
          data-testid="preview-criterion-detail"
        >
          {detailSummaryText}
        </p>
      </div>

      <div className="flex items-center justify-between gap-2">
        <span className={`text-[11px] font-semibold ${metaClass}`}>{metaText}</span>
        {sources.length > 0 ? (
          <button
            type="button"
            title={sources.length === 1 ? `Ver fuente en el pliego (pág. ${sources[0].page})` : "Ver fuentes en el pliego"}
            aria-label={sources.length === 1 ? `Ver fuente en el pliego (pág. ${sources[0].page})` : "Ver fuentes en el pliego"}
            className="inline-flex h-[26px] items-center gap-[5px] rounded-full border border-[rgba(0,60,107,.12)] bg-white px-2 text-[11px] font-semibold text-[#0099DB] transition-colors hover:border-[#0099DB]"
            onClick={handleViewSource}
          >
            <Eye className="h-[13px] w-[13px]" aria-hidden="true" />
            {sources.length === 1 ? `pág. ${sources[0].page}` : `${sources.length} fuentes`}
          </button>
        ) : null}
      </div>
    </article>
  );
}
