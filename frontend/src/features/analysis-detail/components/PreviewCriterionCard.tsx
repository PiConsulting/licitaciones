import { ChevronDown, ChevronUp, Info, Minus } from "lucide-react";
import { useState } from "react";

import type { Citation, NarrativeBulletItem, NarrativeSource } from "../types";
import { sourceToCitation } from "../utils/resolveNarrativeSources";
import { splitLabelAndValue } from "../utils/splitLabelAndValue";
import { PREVIEW_CRITERION_ICONS } from "../utils/previewCriterionIcons";
import { SourceEyeButton } from "./SourceEyeButton";

interface PreviewCriterionCardProps {
  title: string;
  resumen: string | undefined;
  bulletItem: NarrativeBulletItem;
  sources: NarrativeSource[];
  contentId?: string;
  onViewSource?: (payload: { citation: Citation; citations: Citation[]; sources: NarrativeSource[] }) => void;
}

export function PreviewCriterionCard({
  title,
  resumen,
  bulletItem,
  sources,
  contentId,
  onViewSource,
}: PreviewCriterionCardProps) {
  const [expanded, setExpanded] = useState(false);
  const generatedContentId = `preview-criterion-content-${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  const resolvedContentId = contentId ?? generatedContentId;

  const safeResumen = resumen ?? "—";
  const isMuted = safeResumen === "No informado" || safeResumen === "—";
  const Icon = PREVIEW_CRITERION_ICONS[title] ?? Info;
  const detailText = splitLabelAndValue(bulletItem.text)?.value ?? bulletItem.text;

  const handleViewSource = () => {
    if (!onViewSource || sources.length === 0) {
      return;
    }
    const citations = sources.map(sourceToCitation);
    onViewSource({ citation: citations[0], citations, sources });
  };

  return (
    <article
      className={`relative flex-[1_1_220px] max-w-full overflow-hidden rounded-xl border bg-white p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md ${
        isMuted ? "border-dashed border-gray-300" : "border-gray-200"
      }`}
      data-testid="preview-criterion-card"
    >
      <div
        className={`flex h-8 w-8 items-center justify-center rounded-lg ${
          isMuted ? "bg-gray-100 text-gray-400" : "bg-cedia-primary/10 text-cedia-primary"
        }`}
        aria-hidden="true"
      >
        <Icon className="h-4 w-4" />
      </div>

      <div className="mt-3 flex flex-col gap-1 pr-6">
        <h4
          className="text-[10px] font-semibold uppercase tracking-wide text-gray-500"
          data-testid="preview-criterion-title"
        >
          {title}
        </h4>
        {!expanded ? (
          isMuted ? (
            <p
              className="flex items-center gap-1.5 text-sm italic text-gray-400"
              data-testid="preview-criterion-summary"
            >
              <Minus className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
              {safeResumen}
            </p>
          ) : (
            <p
              className="break-words text-sm font-semibold text-gray-700 sm:text-base"
              data-testid="preview-criterion-summary"
            >
              {safeResumen}
            </p>
          )
        ) : null}
      </div>

      {expanded ? (
        <div id={resolvedContentId} className="mt-2 rounded-md bg-gray-50 p-2" data-testid="preview-criterion-detail">
          <p className="break-words text-xs leading-relaxed text-gray-600">{detailText}</p>
          {sources.length > 0 ? (
            <div className="mt-1.5 flex justify-start">
              <SourceEyeButton pages={sources.map((source) => source.page)} onClick={handleViewSource} />
            </div>
          ) : null}
        </div>
      ) : null}

      <button
        type="button"
        className="absolute right-2 top-2 inline-flex h-6 w-6 items-center justify-center rounded-full text-gray-400 transition-colors hover:bg-gray-100 hover:text-cedia-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
        aria-expanded={expanded}
        aria-controls={resolvedContentId}
        aria-label={expanded ? "Colapsar detalle" : "Expandir detalle"}
        title={expanded ? "Colapsar detalle" : "Expandir detalle"}
        onClick={() => setExpanded((value) => !value)}
      >
        {expanded ? <ChevronUp className="h-3.5 w-3.5" aria-hidden="true" /> : <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />}
      </button>
    </article>
  );
}
