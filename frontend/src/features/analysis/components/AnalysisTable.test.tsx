import { fireEvent, render, screen } from "@testing-library/react";

import type { AnalysisListItem } from "../../../types/analysis";
import { AnalysisTable } from "./AnalysisTable";

function buildItem(overrides?: Partial<AnalysisListItem>): AnalysisListItem {
  return {
    id: "analysis-1",
    status: "analyzing",
    current_stage: "analyzing",
    stage_progress: "Analizando categorías",
    progress_percentage: 45,
    created_at: "2026-08-06T10:00:00Z",
    primary_document_name: "Pliego Hospital.pdf",
    organismo: "Ministerio de Salud",
    confidence_avg: 0.82,
    ...overrides,
  };
}

describe("AnalysisTable", () => {
  test("renderiza columnas y filas del historial", () => {
    render(
      <AnalysisTable
        items={[buildItem()]}
        sortBy="created_at"
        sortOrder="desc"
        onSort={() => undefined}
        onRowClick={() => undefined}
        onRetryAnalysis={() => undefined}
        retryingAnalysisId={null}
      />,
    );

    expect(screen.getByText("Pliego Hospital.pdf")).toBeInTheDocument();
    expect(screen.getByText("Ministerio de Salud")).toBeInTheDocument();
    expect(screen.getByText("45%")).toBeInTheDocument();
  });

  test("click en encabezado dispara sorting server-side", () => {
    const onSort = vi.fn();

    render(
      <AnalysisTable
        items={[buildItem()]}
        sortBy="created_at"
        sortOrder="desc"
        onSort={onSort}
        onRowClick={() => undefined}
        onRetryAnalysis={() => undefined}
        retryingAnalysisId={null}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /estado/i }));
    expect(onSort).toHaveBeenCalledWith("status");
  });

  test("badges de estado aplican colores del design system", () => {
    render(
      <AnalysisTable
        items={[buildItem({ status: "error" })]}
        sortBy="created_at"
        sortOrder="desc"
        onSort={() => undefined}
        onRowClick={() => undefined}
        onRetryAnalysis={() => undefined}
        retryingAnalysisId={null}
      />,
    );

    const badge = screen.getByText("Error");
    expect(badge).toHaveClass("bg-error-light", "text-error");
  });

  test("click en fila navega al detalle", () => {
    const onRowClick = vi.fn();

    render(
      <AnalysisTable
        items={[buildItem({ status: "completed" })]}
        sortBy="created_at"
        sortOrder="desc"
        onSort={() => undefined}
        onRowClick={onRowClick}
        onRetryAnalysis={() => undefined}
        retryingAnalysisId={null}
      />,
    );

    fireEvent.click(screen.getByText("Pliego Hospital.pdf"));
    expect(onRowClick).toHaveBeenCalledWith("analysis-1");
  });

  test("click en acción de eliminar no navega", () => {
    const onRowClick = vi.fn();
    const onDeleteAnalysis = vi.fn();

    render(
      <AnalysisTable
        items={[buildItem({ status: "completed" })]}
        sortBy="created_at"
        sortOrder="desc"
        onSort={() => undefined}
        onRowClick={onRowClick}
        onRetryAnalysis={() => undefined}
        onDeleteAnalysis={onDeleteAnalysis}
        retryingAnalysisId={null}
        deletingAnalysisId={null}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /eliminar análisis/i }));
    expect(onRowClick).not.toHaveBeenCalled();
    expect(onDeleteAnalysis).toHaveBeenCalled();
  });

  test("muestra icono reintentar y ejecuta callback cuando el estado es error", () => {
    const onRetryAnalysis = vi.fn();

    render(
      <AnalysisTable
        items={[buildItem({ status: "error" })]}
        sortBy="created_at"
        sortOrder="desc"
        onSort={() => undefined}
        onRowClick={() => undefined}
        onRetryAnalysis={onRetryAnalysis}
        retryingAnalysisId={null}
        deletingAnalysisId={null}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /reintentar análisis/i }));
    expect(onRetryAnalysis).toHaveBeenCalledWith("analysis-1");
  });

  test("muestra icono eliminar cuando el análisis no está en curso", () => {
    render(
      <AnalysisTable
        items={[buildItem({ status: "analyzing" })]}
        sortBy="created_at"
        sortOrder="desc"
        onSort={() => undefined}
        onRowClick={() => undefined}
        onRetryAnalysis={() => undefined}
        retryingAnalysisId={null}
        deletingAnalysisId={null}
      />,
    );

    expect(screen.queryByRole("button", { name: /eliminar análisis/i })).not.toBeInTheDocument();
  });

  test("muestra icono eliminar para análisis completado", () => {
    render(
      <AnalysisTable
        items={[buildItem({ status: "completed" })]}
        sortBy="created_at"
        sortOrder="desc"
        onSort={() => undefined}
        onRowClick={() => undefined}
        onRetryAnalysis={() => undefined}
        retryingAnalysisId={null}
        deletingAnalysisId={null}
      />,
    );

    expect(screen.getByRole("button", { name: /eliminar análisis/i })).toBeInTheDocument();
  });
});
