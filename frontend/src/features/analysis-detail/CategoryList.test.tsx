import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { CategoryList } from "./CategoryList";
import { CATEGORY_NAMES, CATEGORY_ORDER } from "../../utils/categoryIcons";
import type { AnalysisDetail, CategoryData } from "./types";

const mockAnalysis: AnalysisDetail = {
  id: "test-analysis",
  status: "completed",
  created_at: "2026-08-06T12:00:00Z",
  created_by: "test-user",
  current_stage: null,
  correlation_id: "test-correlation",
  documents: [],
  current_version: {
    id: "version-1",
    version_number: 1,
    created_at: "2026-08-06T12:00:00Z",
    extracted_data: {
      objeto_alcance: {
        items: [{ field_name: "test", field_value: "test", field_state: "extraido", citations: [] }],
        confidence: 0.9,
        source_references: [],
        extraction_status: "completed",
        summary: "Test summary",
        is_reviewed: false,
      } as CategoryData,
      riesgos: {
        items: [],
        confidence: 0,
        source_references: [],
        extraction_status: "completed",
        summary: "Sin datos",
        is_reviewed: false,
      } as CategoryData,
      requisitos_admisibilidad: {
        items: [],
        confidence: 0,
        source_references: [],
        extraction_status: "completed",
        summary: "Sin datos",
        is_reviewed: false,
      } as CategoryData,
      garantias: {
        items: [],
        confidence: 0,
        source_references: [],
        extraction_status: "completed",
        summary: "Sin datos",
        is_reviewed: false,
      } as CategoryData,
      plazos_clave: {
        items: [],
        confidence: 0,
        source_references: [],
        extraction_status: "completed",
        summary: "Sin datos",
        is_reviewed: false,
      } as CategoryData,
      criterios_evaluacion: {
        items: [],
        confidence: 0,
        source_references: [],
        extraction_status: "completed",
        summary: "Sin datos",
        is_reviewed: false,
      } as CategoryData,
      causales_rechazo: {
        items: [],
        confidence: 0,
        source_references: [],
        extraction_status: "completed",
        summary: "Sin datos",
        is_reviewed: false,
      } as CategoryData,
      anexos_obligatorios: {
        items: [],
        confidence: 0,
        source_references: [],
        extraction_status: "completed",
        summary: "Sin datos",
        is_reviewed: false,
      } as CategoryData,
    },
  },
};

describe("CategoryList - AC3: Orden consistente en todos los componentes", () => {
  it("debe renderizar categorías en el orden canónico exacto", () => {
    const { container } = render(<CategoryList analysis={mockAnalysis} />);

    const articles = container.querySelectorAll("article");
    expect(articles).toHaveLength(8);

    CATEGORY_ORDER.forEach((categoryId, index) => {
      expect(articles[index].id).toBe(`category-${categoryId}`);
    });
  });

  it("debe mostrar nombres de categorías en el orden canónico", () => {
    render(<CategoryList analysis={mockAnalysis} />);

    const headings = screen.getAllByRole("heading", { level: 3 });
    expect(headings).toHaveLength(8);

    CATEGORY_ORDER.forEach((categoryId, index) => {
      expect(headings[index]).toHaveTextContent(CATEGORY_NAMES[categoryId]);
    });
  });

  it("NO debe renderizar datos_procedimiento", () => {
    render(<CategoryList analysis={mockAnalysis} />);

    const datasProcArticle = document.getElementById("category-datos_procedimiento");
    expect(datasProcArticle).toBeNull();

    expect(screen.queryByText("Datos del Procedimiento")).toBeNull();
  });
});

describe("CategoryList - AC5: Compatibilidad con categorías faltantes", () => {
  it("debe renderizar todas las 8 categorías aunque el backend no envíe datos", () => {
    const emptyAnalysis: AnalysisDetail = {
      ...mockAnalysis,
      current_version: {
        id: "version-1",
        version_number: 1,
        created_at: "2026-08-06T12:00:00Z",
        extracted_data: {},
      },
    };

    const { container } = render(<CategoryList analysis={emptyAnalysis} />);

    const articles = container.querySelectorAll("article");
    expect(articles).toHaveLength(8);

    CATEGORY_ORDER.forEach((categoryId) => {
      const article = document.getElementById(`category-${categoryId}`);
      expect(article).not.toBeNull();
    });

    // Sin datos, `CategoryList` completa con `EMPTY_CATEGORY` (`not_analyzed`): se muestra minimalista, no como "sin evidencia" (afirmaría que se buscó y no se encontró nada).
    expect(screen.queryAllByTestId("narrative-blocks")).toHaveLength(0);
    expect(document.getElementById("category-plazos_clave")?.querySelector('[data-testid^="plazos-timeline"]')).toBeNull();
    expect(screen.getAllByTestId("category-not-analyzed")).toHaveLength(8);
  });

  it("debe renderizar categorías con datos parciales sin errores", () => {
    const partialAnalysis: AnalysisDetail = {
      ...mockAnalysis,
      current_version: {
        id: "version-1",
        version_number: 1,
        created_at: "2026-08-06T12:00:00Z",
        extracted_data: {
          objeto_alcance: mockAnalysis.current_version!.extracted_data.objeto_alcance,
          garantias: mockAnalysis.current_version!.extracted_data.garantias,
        },
      },
    };

    const { container } = render(<CategoryList analysis={partialAnalysis} />);

    const articles = container.querySelectorAll("article");
    expect(articles).toHaveLength(8);

    expect(screen.getByText("Objeto y Alcance")).toBeInTheDocument();
    expect(screen.getByText("Garantías")).toBeInTheDocument();
    expect(screen.getByText("Plazos Clave")).toBeInTheDocument();
    expect(screen.getByText("Requisitos de Admisibilidad")).toBeInTheDocument();

    // Solo las 2 categorías con datos reales tienen NarrativeBlocks; las faltantes (`not_analyzed` vía `EMPTY_CATEGORY`) se muestran minimalistas.
    const narrativeBlocks = screen.getAllByTestId("narrative-blocks");
    expect(narrativeBlocks).toHaveLength(2);
    expect(document.getElementById("category-plazos_clave")?.querySelector('[data-testid^="plazos-timeline"]')).toBeNull();
    expect(screen.getAllByTestId("category-not-analyzed")).toHaveLength(6);
  });
});
