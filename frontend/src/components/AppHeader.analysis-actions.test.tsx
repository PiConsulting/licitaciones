import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import { AppHeader } from "./AppHeader";
import type { AnalysisDetail } from "../features/analysis-detail/types";
import type { AnalysisTracking } from "../types/tracking";

function createTracking(status: AnalysisTracking["status"]): AnalysisTracking {
  return {
    id: "tracking-1",
    type: "tracking",
    analysis_id: "analysis-1",
    version_id: "v1",
    status,
    started_by: "user-1",
    started_at: "2026-09-10T10:00:00Z",
    updated_at: "2026-09-10T10:00:00Z",
    categories: [],
    summary: { total_categories: 8, not_reviewed: 0, in_review: 8, closed: 0, closed_percentage: 0 },
  };
}

function createAnalysisDetail(status: AnalysisDetail["status"] = "analyzed"): AnalysisDetail {
  return {
    id: "analysis-1",
    created_at: "2026-09-10T10:00:00Z",
    status,
    current_stage: "completed",
    analysis_name: "LP 12/2026",
    current_version: {
      id: "v1",
      version_number: 1,
      extracted_data: {
        objeto_alcance: { items: [], confidence: 0, source_references: [], extraction_status: "not_found", summary: "", is_reviewed: false },
        riesgos: { items: [], confidence: 0, source_references: [], extraction_status: "not_found", summary: "", is_reviewed: false },
        requisitos_admisibilidad: { items: [], confidence: 0, source_references: [], extraction_status: "not_found", summary: "", is_reviewed: false },
        garantias: { items: [], confidence: 0, source_references: [], extraction_status: "not_found", summary: "", is_reviewed: false },
        plazos_clave: { items: [], confidence: 0, source_references: [], extraction_status: "not_found", summary: "", is_reviewed: false },
        criterios_evaluacion: { items: [], confidence: 0, source_references: [], extraction_status: "not_found", summary: "", is_reviewed: false },
        causales_rechazo: { items: [], confidence: 0, source_references: [], extraction_status: "not_found", summary: "", is_reviewed: false },
        anexos_obligatorios: { items: [], confidence: 0, source_references: [], extraction_status: "not_found", summary: "", is_reviewed: false },
        datos_procedimiento: { items: [], confidence: 0, source_references: [], extraction_status: "not_found", summary: "", is_reviewed: false },
      },
      conflicts: {},
      created_at: "2026-09-10T10:00:00Z",
    },
    documents: [{ id: "doc-1", filename: "Pliego.pdf", is_primary: true, page_count: 12 }],
  };
}

function renderHeader(status: AnalysisDetail["status"] = "analyzed") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(["analysis", "analysis-1", "detail"], createAnalysisDetail(status));

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/analysis/analysis-1"]}>
        <Routes>
          <Route path="/analysis/:analysisId" element={<AppHeader />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderChecklistHeader(tracking: AnalysisTracking) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(["analysis", "analysis-1", "detail"], { ...createAnalysisDetail("analyzed"), tracking });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/analysis/analysis-1/checklist"]}>
        <Routes>
          <Route path="/analysis/:analysisId/checklist" element={<AppHeader />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AppHeader - acciones en breadcrumb de análisis", () => {
  test("muestra acciones Ocultar PDF, Checklist de seguimiento y Reanalizar", () => {
    renderHeader("analyzed");

    expect(screen.getByRole("button", { name: /Ocultar PDF/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Checklist de seguimiento/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reanalizar/i })).toBeInTheDocument();
  });

  test("sin analysis_name cargado a mano, el breadcrumb usa el mismo título corto que el H1 en vez de 'Análisis <id>'", () => {
    // Bug real reportado: la mayoría de los análisis no tiene `analysis_name`
    // -- el breadcrumb sólo miraba ese campo y el filename, así que caía
    // directo a "Análisis <id>" aunque el título de la página ya mostrara
    // tipo/número de procedimiento.
    const analysis = createAnalysisDetail("analyzed");
    const withDatosProcedimiento: AnalysisDetail = {
      ...analysis,
      analysis_name: undefined,
      current_version: {
        ...analysis.current_version,
        extracted_data: {
          ...analysis.current_version.extracted_data,
          datos_procedimiento: {
            items: [
              {
                field_name: "Tipo de procedimiento",
                field_value: "Licitación Pública",
                field_state: "extraido",
                confidence: 0.9,
                citations: [],
              },
              {
                field_name: "Procedimiento",
                field_value: "N° 45/2026",
                field_state: "extraido",
                confidence: 0.9,
                citations: [],
              },
            ],
            confidence: 0.9,
            source_references: [],
            extraction_status: "success",
            summary: "",
            is_reviewed: false,
          },
        },
      },
    };

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    queryClient.setQueryData(["analysis", "analysis-1", "detail"], withDatosProcedimiento);

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/analysis/analysis-1"]}>
          <Routes>
            <Route path="/analysis/:analysisId" element={<AppHeader />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText("Licitación Pública — N° 45/2026")).toBeInTheDocument();
    expect(screen.queryByText(/^Análisis analysis-1/)).not.toBeInTheDocument();
  });
});

describe("AppHeader - breadcrumb de checklist de cumplimiento", () => {
  test("muestra CedIA / Licitaciones / análisis / Checklist de cumplimiento con enlaces", () => {
    renderChecklistHeader(createTracking("active"));

    const nav = screen.getByRole("navigation", { name: "Ruta de navegación" });
    expect(nav).toHaveTextContent("CedIA");

    const licitacionesLink = screen.getByRole("link", { name: "Licitaciones" });
    expect(licitacionesLink).toHaveAttribute("href", "/");

    const analysisLink = screen.getByRole("link", { name: "LP 12/2026" });
    expect(analysisLink).toHaveAttribute("href", "/analysis/analysis-1");

    expect(screen.getByText("Checklist de cumplimiento")).toBeInTheDocument();
  });

  test("con seguimiento activo, muestra el botón Completar seguimiento", () => {
    renderChecklistHeader(createTracking("active"));

    expect(screen.getByText("Seguimiento activo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Completar seguimiento" })).toBeInTheDocument();
  });

  test("con seguimiento completado, oculta Completar seguimiento y ofrece Reanudar seguimiento", () => {
    renderChecklistHeader(createTracking("completed"));

    expect(screen.getByText("Seguimiento finalizado")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Completar seguimiento" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reanudar seguimiento" })).toBeInTheDocument();
  });

  test("con seguimiento activo no ofrece Reanudar seguimiento", () => {
    renderChecklistHeader(createTracking("active"));

    expect(screen.queryByRole("button", { name: "Reanudar seguimiento" })).not.toBeInTheDocument();
  });

  test("Reanudar seguimiento emite el evento para que el checklist reanude", () => {
    const handler = vi.fn();
    window.addEventListener("checklist:resume-tracking", handler);
    renderChecklistHeader(createTracking("completed"));

    fireEvent.click(screen.getByRole("button", { name: "Reanudar seguimiento" }));

    expect(handler).toHaveBeenCalledTimes(1);
    window.removeEventListener("checklist:resume-tracking", handler);
  });

  test("no muestra Ocultar PDF, Checklist de seguimiento ni Reanalizar en la página de checklist", () => {
    renderChecklistHeader(createTracking("active"));

    expect(screen.queryByRole("button", { name: /Ocultar PDF/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Checklist de seguimiento$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Reanalizar$/i })).not.toBeInTheDocument();
  });
});
