import { Badge } from "../../components/Badge";
import type { AnalysisDetail } from "./types";
import { getAnalysisSummary } from "./utils/categoryStats";

interface AnalysisSummaryStripProps {
  analysis: AnalysisDetail;
}

export function AnalysisSummaryStrip({ analysis }: AnalysisSummaryStripProps) {
  const summary = getAnalysisSummary(analysis);

  return (
    <section aria-label="Resumen de extracción" className="mb-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs font-medium text-gray-600">
          {`${summary.extractedCategories}/${summary.totalCategories} categorías extraídas`}
        </p>
        {summary.conflict > 0 ? <Badge tone="error">{`${summary.conflict} conflictos`}</Badge> : null}
        {summary.notFound > 0 ? <Badge tone="warning">{`${summary.notFound} no encontrados`}</Badge> : null}
      </div>
    </section>
  );
}
