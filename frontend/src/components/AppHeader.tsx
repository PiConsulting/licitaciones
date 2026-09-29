import { ChevronRight, Plus } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation, useMatch } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";

import { buildAnalysisShortTitle } from "../features/analysis-detail/utils/analysisFields";
import { getAnalysisById } from "../services/api/analysisApi";

const PAGE_TITLES: Array<{ prefix: string; title: string }> = [
  { prefix: "/analyze", title: "Analizar nuevo pliego" },
  { prefix: "/analysis", title: "Análisis IA" },
];

function getPageTitle(pathname: string): string {
  const match = PAGE_TITLES.find(({ prefix }) => pathname.startsWith(prefix));
  return match?.title ?? "CedIA";
}

export function AppHeader() {
  const location = useLocation();
  const title = getPageTitle(location.pathname);
  const isAnalyzePage = location.pathname.startsWith("/analyze");
  const isDashboardPage = location.pathname === "/";
  const detailMatch = useMatch("/analysis/:analysisId");
  const checklistMatch = useMatch("/analysis/:analysisId/checklist");
  const isChecklistPage = Boolean(checklistMatch);
  const analysisId = detailMatch?.params.analysisId ?? checklistMatch?.params.analysisId;

  // Suscripto (no `getQueryData` suelto) para que el header se re-renderice cuando
  // `AnalysisDetailPage` termina de traer los datos -- si no, el botón Reanalizar
  // sólo aparecía si algo más forzaba un re-render del header después del fetch.
  const { data: detailData } = useQuery({
    queryKey: ["analysis", analysisId, "detail"],
    queryFn: () => getAnalysisById(analysisId as string),
    enabled: Boolean(analysisId),
    staleTime: 1000 * 60 * 5,
  });
  // Antes solo miraba `analysis_name`/filename -- para cualquier análisis sin
  // nombre cargado a mano (la mayoría) mostraba "Análisis <id>" aunque el
  // título de la página ya mostrara algo con sentido (tipo/número de
  // procedimiento, denominación u organismo). Misma lógica que el H1.
  const breadcrumbLabel = detailData ? buildAnalysisShortTitle(detailData) : analysisId ? `Análisis ${analysisId.slice(0, 8)}` : "Detalle";
  const trackingStatus = detailData?.tracking?.status;

  const [isPdfVisible, setIsPdfVisible] = useState(true);

  useEffect(() => {
    const handlePdfVisibility = (event: Event) => {
      const customEvent = event as CustomEvent<{ visible?: boolean }>;
      if (typeof customEvent.detail?.visible === "boolean") {
        setIsPdfVisible(customEvent.detail.visible);
      }
    };

    window.addEventListener("analysis-detail:pdf-visibility", handlePdfVisibility);
    return () => {
      window.removeEventListener("analysis-detail:pdf-visibility", handlePdfVisibility);
    };
  }, []);

  const canReanalyze = useMemo(() => {
    if (!detailData) {
      return false;
    }
    return (
      detailData.status === "en_revision" ||
      detailData.status === "analyzed" ||
      detailData.status === "validated" ||
      detailData.status === "error"
    );
  }, [detailData]);

  if (isAnalyzePage) {
    return (
      <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b border-cedi-navy-12 bg-white px-6">
        <div className="flex items-center gap-2.5">
          <span className="font-display text-[15px] font-bold text-cedi-navy">CedIA</span>
          <span className="h-4 w-px bg-cedi-navy-20" aria-hidden="true" />
          <span className="text-[13px] font-medium text-cedi-navy-68">Analizar nuevo pliego</span>
        </div>
        <Link to="/" className="text-[13px] font-semibold text-cedi-celeste hover:text-cedi-navy">
          Cancelar y volver
        </Link>
      </header>
    );
  }

  if (isDashboardPage) {
    return (
      <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b border-cedi-navy-12 bg-white px-6">
        <div className="flex items-center gap-2.5">
          <span className="font-display text-[15px] font-bold text-cedi-navy">CedIA</span>
          <span className="h-4 w-px bg-cedi-navy-20" aria-hidden="true" />
          <span className="text-[13px] font-medium text-cedi-navy-68">Home</span>
        </div>
        <Link
          to="/analyze"
          className="inline-flex h-9 items-center gap-2 whitespace-nowrap rounded-full bg-gradient-to-r from-[#2F4EF8] to-[#A966FF] px-5 text-[13px] font-semibold text-white hover:bg-none hover:bg-cedi-navy"
        >
          <Plus className="h-3.5 w-3.5" strokeWidth={2.5} aria-hidden="true" />
          Analizar nuevo pliego
        </Link>
      </header>
    );
  }

  if (isChecklistPage) {
    const isTrackingCompleted = trackingStatus === "completed";
    return (
      <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b border-cedi-navy-12 bg-white px-6">
        <nav aria-label="Ruta de navegación" className="flex min-w-0 items-center gap-2 text-[13px]">
          <span className="font-display text-[15px] font-bold text-cedi-navy">CedIA</span>
          <span className="h-4 w-px bg-cedi-navy-20" aria-hidden="true" />
          <Link to="/" className="font-medium text-cedi-navy-68 hover:text-cedi-navy">
            Licitaciones
          </Link>
          <ChevronRight className="h-3.5 w-3.5 text-cedi-navy-68" aria-hidden="true" />
          <Link to={`/analysis/${analysisId}`} className="truncate font-medium text-cedi-navy-68 hover:text-cedi-navy">
            {breadcrumbLabel}
          </Link>
          <ChevronRight className="h-3.5 w-3.5 text-cedi-navy-68" aria-hidden="true" />
          <span className="truncate font-semibold text-cedi-navy">Checklist de cumplimiento</span>
        </nav>
        <div className="flex items-center gap-2">
          <span
            className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-[5px] text-xs font-semibold"
            style={{
              backgroundColor: isTrackingCompleted ? "rgba(0,60,107,.08)" : "rgba(127,243,222,.35)",
              color: isTrackingCompleted ? "rgba(0,60,107,.68)" : "#0B6B58",
            }}
          >
            <span
              className="h-[7px] w-[7px] rounded-full"
              style={{ backgroundColor: isTrackingCompleted ? "rgba(0,60,107,.4)" : "#1FC9A8" }}
            />
            {isTrackingCompleted ? "Seguimiento finalizado" : "Seguimiento activo"}
          </span>
          {isTrackingCompleted ? (
            <button
              type="button"
              onClick={() => window.dispatchEvent(new CustomEvent("checklist:resume-tracking"))}
              className="inline-flex h-9 items-center rounded-full bg-gradient-to-r from-[#2F4EF8] to-[#A966FF] px-4 text-[13px] font-semibold text-white hover:brightness-110"
            >
              Reanudar seguimiento
            </button>
          ) : (
            <button
              type="button"
              onClick={() => window.dispatchEvent(new CustomEvent("checklist:complete-tracking"))}
              className="inline-flex h-9 items-center rounded-full bg-gradient-to-r from-[#2F4EF8] to-[#A966FF] px-4 text-[13px] font-semibold text-white hover:brightness-110"
            >
              Completar seguimiento
            </button>
          )}
        </div>
      </header>
    );
  }

  if (analysisId) {
    return (
      <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b border-cedi-navy-12 bg-white px-6">
        <nav aria-label="Ruta de navegación" className="flex min-w-0 items-center gap-2 text-[13px]">
          <span className="font-display text-[15px] font-bold text-cedi-navy">CedIA</span>
          <span className="h-4 w-px bg-cedi-navy-20" aria-hidden="true" />
          <Link to="/" className="font-medium text-cedi-navy-68 hover:text-cedi-navy">
            Licitaciones
          </Link>
          <ChevronRight className="h-3.5 w-3.5 text-cedi-navy-68" aria-hidden="true" />
          <span className="truncate font-semibold text-cedi-navy">{breadcrumbLabel}</span>
        </nav>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => window.dispatchEvent(new CustomEvent("analysis-detail:toggle-pdf"))}
            className="inline-flex h-9 items-center gap-2 rounded-full border-[1.5px] border-[rgba(0,60,107,.2)] bg-white px-3.5 text-[13px] font-semibold text-[#003C6B] hover:border-[#0099DB]"
          >
            {isPdfVisible ? "Ocultar PDF" : "Mostrar PDF"}
          </button>
          <button
            type="button"
            onClick={() => window.dispatchEvent(new CustomEvent("analysis-detail:open-checklist"))}
            className="inline-flex h-9 items-center rounded-full bg-gradient-to-r from-[#2F4EF8] to-[#A966FF] px-4 text-[13px] font-semibold text-white hover:brightness-110"
          >
            Checklist de seguimiento
          </button>
          {canReanalyze ? (
            <button
              type="button"
              onClick={() => window.dispatchEvent(new CustomEvent("analysis-detail:open-reanalyze"))}
              className="inline-flex h-9 items-center rounded-full border-[1.5px] border-[rgba(0,60,107,.2)] bg-white px-3.5 text-[13px] font-semibold text-[#003C6B] hover:border-[#0099DB]"
            >
              Reanalizar
            </button>
          ) : null}
        </div>
      </header>
    );
  }

  return (
    <header className="sticky top-0 z-10 flex h-14 items-center border-b border-gray-200 bg-surface px-6">
      <h1 className="text-sm font-semibold text-gray-900">{title}</h1>
    </header>
  );
}
