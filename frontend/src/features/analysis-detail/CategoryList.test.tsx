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

    // Verificar que cada artículo tiene el ID correcto en el orden esperado
    CATEGORY_ORDER.forEach((categoryId, index) => {
      expect(articles[index].id).toBe(`category-${categoryId}`);
    });
  });

  it("debe mostrar nombres de categorías en el orden canónico", () => {
    render(<CategoryList analysis={mockAnalysis} />);

    // Obtener todos los h3 (nombres de categorías) en orden de aparición
    const headings = screen.getAllByRole("heading", { level: 3 });
    expect(headings).toHaveLength(8);

    // Verificar que cada heading tiene el nombre correcto en el orden esperado
    CATEGORY_ORDER.forEach((categoryId, index) => {
      expect(headings[index]).toHaveTextContent(CATEGORY_NAMES[categoryId]);
    });
  });

  it("NO debe renderizar datos_procedimiento", () => {
    render(<CategoryList analysis={mockAnalysis} />);

    // Verificar que no existe el artículo de datos_procedimiento
    const datasProcArticle = document.getElementById("category-datos_procedimiento");
    expect(datasProcArticle).toBeNull();

    // Verificar que el nombre no aparece
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
        extracted_data: {}, // Sin datos del backend
      },
    };

    const { container } = render(<CategoryList analysis={emptyAnalysis} />);

    const articles = container.querySelectorAll("article");
    expect(articles).toHaveLength(8);

    // Verificar que todas las categorías se muestran
    CATEGORY_ORDER.forEach((categoryId) => {
      const article = document.getElementById(`category-${categoryId}`);
      expect(article).not.toBeNull();
    });

    // Sin datos del backend, `CategoryList` completa con `EMPTY_CATEGORY`
    // (`extraction_status: "not_analyzed"`): las 8 categorías, incluida
    // Plazos Clave, se muestran en minimalista -- no como un contenedor de
    // "Respuesta" vacío ni una timeline vacía, que sugerirían que se buscó y
    // no se encontró nada.
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
          // Solo 2 categorías, las otras 6 faltantes
        },
      },
    };

    const { container } = render(<CategoryList analysis={partialAnalysis} />);

    const articles = container.querySelectorAll("article");
    expect(articles).toHaveLength(8); // Siempre 8 categorías

    // Verificar que las categorías con datos y sin datos se renderizan
    expect(screen.getByText("Objeto y Alcance")).toBeInTheDocument();
    expect(screen.getByText("Garantías")).toBeInTheDocument();
    expect(screen.getByText("Plazos Clave")).toBeInTheDocument(); // Sin datos pero renderizada
    expect(screen.getByText("Requisitos de Admisibilidad")).toBeInTheDocument(); // Sin datos pero renderizada

    // Sólo las 2 categorías con datos reales (objeto_alcance, garantias)
    // tienen NarrativeBlocks; las otras 6 -- faltantes, `not_analyzed` vía
    // `EMPTY_CATEGORY` -- se muestran en minimalista, no como timeline/
    // contenedor vacío.
    const narrativeBlocks = screen.getAllByTestId("narrative-blocks");
    expect(narrativeBlocks).toHaveLength(2);
    expect(document.getElementById("category-plazos_clave")?.querySelector('[data-testid^="plazos-timeline"]')).toBeNull();
    expect(screen.getAllByTestId("category-not-analyzed")).toHaveLength(6);
  });
});
