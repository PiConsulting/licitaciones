import { useParams } from "react-router-dom";

export default function AnalysisDetail() {
  const { analysisId } = useParams();

  return (
    <section>
      <h1 className="text-2xl font-semibold">Detalle del análisis</h1>
      <p className="mt-2 text-sm text-gray-600">Análisis seleccionado: {analysisId}</p>
      <p className="mt-1 text-sm text-gray-600">La vista completa de resultados se implementará en las siguientes historias.</p>
    </section>
  );
}
