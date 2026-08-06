import { Eye } from "lucide-react";

import { ActionButton } from "../ActionButton";
import type { Citation } from "../types";
import type { NarrativeSynthesis } from "../utils/narrativeSynthesis";

interface NarrativeBlockProps {
  synthesis: NarrativeSynthesis;
  citations: Citation[];
  onViewSource?: (payload: { citation: Citation; citations: Citation[] }) => void;
}

export function NarrativeBlock({ synthesis, citations, onViewSource }: NarrativeBlockProps) {
  const representativeCitation = synthesis.representativeCitation;
  const evidenceCitations = citations.filter(
    (citation) => citation.document_id.trim() && citation.page > 0 && citation.text.trim(),
  );

  const handleViewSource = (citation: Citation) => {
    if (!onViewSource) {
      return;
    }
    onViewSource({ citation, citations: evidenceCitations });
  };

  return (
    <section className="mt-3 rounded-md border border-gray-200 bg-gray-50 p-3" data-testid="narrative-block">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-700">Sintesis</h4>

      {synthesis.bullets.length > 0 ? (
        <div className="mt-2 space-y-2 text-sm leading-relaxed text-gray-800">
          {synthesis.intro ? <p>{synthesis.intro}</p> : null}
          <ul className="list-disc space-y-1 pl-5" data-testid="narrative-bullets">
            {synthesis.bullets.map((bullet, index) => (
              <li key={`${bullet}-${index}`}>{bullet}</li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-2 text-sm leading-relaxed text-gray-800">{synthesis.text}</p>
      )}

      {representativeCitation ? (
        <div className="mt-3 rounded border border-gray-200 bg-white p-2" data-testid="narrative-source">
          <p className="text-xs text-gray-600">
            Fuente representativa: {representativeCitation.document_name} (pag. {representativeCitation.page})
          </p>
          <p className="mt-1 text-xs italic text-gray-600">
            "{representativeCitation.text.slice(0, 160)}{representativeCitation.text.length > 160 ? "..." : ""}"
          </p>
          <div className="mt-2">
            <ActionButton
              text="Ver fuente"
              icon={Eye}
              variant="ghost"
              onClick={() => handleViewSource(representativeCitation)}
            />
          </div>
        </div>
      ) : null}

      <div className="mt-3 rounded border border-gray-200 bg-white p-2" data-testid="category-sources">
        <h5 className="text-xs font-semibold uppercase tracking-wide text-gray-700">Fuentes verificables</h5>
        {evidenceCitations.length > 0 ? (
          <ul className="mt-2 space-y-2" data-testid="category-sources-list">
            {evidenceCitations.map((citation, index) => (
              <li key={`${citation.document_id}-${citation.page}-${index}`}>
                <button
                  type="button"
                  className="w-full rounded border border-gray-200 px-2 py-1 text-left text-xs text-primary hover:border-primary"
                  onClick={() => handleViewSource(citation)}
                >
                  <span className="font-semibold">{citation.document_name}</span>
                  <span>{` · pág. ${citation.page}`}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-xs text-gray-600" data-testid="category-sources-empty">
            Sin evidencia clickeable para esta categoría. No puede marcarse como revisada automáticamente.
          </p>
        )}
      </div>
    </section>
  );
}
