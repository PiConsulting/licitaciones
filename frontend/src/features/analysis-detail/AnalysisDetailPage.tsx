import { AnalysisHeader } from "./AnalysisHeader";
import { CategoryList } from "./CategoryList";
import { useAnalysisDetail } from "./hooks/useAnalysisDetail";

interface AnalysisDetailPageProps {
  analysisId: string;
}

export function AnalysisDetailPage({ analysisId }: AnalysisDetailPageProps) {
  const query = useAnalysisDetail(analysisId);

  if (query.isLoading) {
    return <p className="text-sm text-gray-600">Cargando detalle del análisis...</p>;
  }

  if (query.isError) {
    return <p className="text-sm text-error">No se pudo cargar el detalle del análisis.</p>;
  }

  if (!query.data) {
    return <p className="text-sm text-gray-600">No hay datos de análisis disponibles.</p>;
  }

  return (
    <section>
      <AnalysisHeader analysis={query.data} />

      <div className="flex flex-col gap-4 lg:flex-row">
        <div data-testid="categories-panel" className="w-full lg:w-[60%]">
          <CategoryList analysis={query.data} />
        </div>

        <aside
          data-testid="pdf-viewer-panel"
          className="w-full rounded-md border border-dashed border-gray-300 bg-gray-50 p-4 text-sm text-gray-600 lg:w-[40%]"
        >
          Visor PDF reservado para la próxima historia (3-2).
        </aside>
      </div>
    </section>
  );
}
