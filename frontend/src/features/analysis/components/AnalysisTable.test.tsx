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
      />,
    );

    const badge = screen.getByText("Error");
    expect(badge).toHaveClass("bg-error-light", "text-error");
  });

  test("click en fila navega al detalle", () => {
    const onRowClick = vi.fn();

    render(
      <AnalysisTable
        items={[buildItem()]}
        sortBy="created_at"
        sortOrder="desc"
        onSort={() => undefined}
        onRowClick={onRowClick}
      />,
    );

    fireEvent.click(screen.getByText("Pliego Hospital.pdf"));
    expect(onRowClick).toHaveBeenCalledWith("analysis-1");
  });

  test("click en botón menú no navega", () => {
    const onRowClick = vi.fn();

    render(
      <AnalysisTable
        items={[buildItem()]}
        sortBy="created_at"
        sortOrder="desc"
        onSort={() => undefined}
        onRowClick={onRowClick}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /menú/i }));
    expect(onRowClick).not.toHaveBeenCalled();
  });
});
