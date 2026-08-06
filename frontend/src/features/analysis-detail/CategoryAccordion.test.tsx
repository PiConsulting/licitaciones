import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CategoryAccordion } from "./CategoryAccordion";
import { CategoryList } from "./CategoryList";
import { useAccordionState } from "./hooks/useAccordionState";
import type { AnalysisDetail, CategoryData, CategoryId, FieldItem } from "./types";
import { CATEGORY_ICONS } from "../../utils/categoryIcons";

function createField(
  field_name: string,
  options?: {
    state?: FieldItem["field_state"];
    confidence?: number;
    value?: string | null;
  },
): FieldItem {
  return {
    field_name,
    field_value: options?.value ?? field_name,
    field_state: options?.state ?? "extraido",
    confidence: options?.confidence ?? 0.9,
    citations: [
      {
        text: `Cita de ${field_name}`,
        page: 2,
        document_id: "doc-1",
        document_name: "Pliego.pdf",
      },
    ],
  };
}

function createMockCategory(
  categoryId: CategoryId,
  options?: {
    is_reviewed?: boolean;
    extraction_status?: CategoryData["extraction_status"];
    conflictCount?: number;
    extractedCount?: number;
    notFoundCount?: number;
    summary?: string;
    items?: FieldItem[];
  },
): CategoryData {
  if (options?.items) {
    return {
      items: options.items,
      confidence: 0.8,
      source_references: [{ page: 1, document_id: "doc-1", text_snippet: `Resumen ${categoryId}` }],
      extraction_status: options.extraction_status ?? "success",
      summary: options.summary ?? `Resumen de ${categoryId}`,
      is_reviewed: options.is_reviewed ?? false,
    };
  }

  const extracted = options?.extractedCount ?? 2;
  const notFound = options?.notFoundCount ?? 1;
  const conflicts = options?.conflictCount ?? 0;
  const items: FieldItem[] = [];

  for (let i = 0; i < extracted; i += 1) {
    items.push(createField(`extraido-${i + 1}`, { state: "extraido", confidence: 0.9 }));
  }
  for (let i = 0; i < notFound; i += 1) {
    items.push(createField(`no-encontrado-${i + 1}`, { state: "no_encontrado", confidence: 0 }));
  }
  for (let i = 0; i < conflicts; i += 1) {
    items.push(createField(`conflicto-${i + 1}`, { state: "en_conflicto", confidence: 0.4 }));
  }

  return {
    items,
    confidence: 0.75,
    source_references: [{ page: 1, document_id: "doc-1", text_snippet: "Referencia" }],
    extraction_status: options?.extraction_status ?? "success",
    summary: options?.summary ?? `Resumen de ${categoryId}`,
    is_reviewed: options?.is_reviewed ?? false,
  };
}

function createMockAnalysis(): AnalysisDetail {
  const categories = {
    objeto_alcance: createMockCategory("objeto_alcance"),
    requisitos_admisibilidad: createMockCategory("requisitos_admisibilidad"),
    garantias: createMockCategory("garantias", { summary: "Resumen de garantías" }),
    plazos_clave: createMockCategory("plazos_clave", { summary: "Resumen de plazos" }),
    criterios_evaluacion: createMockCategory("criterios_evaluacion"),
    causales_rechazo: createMockCategory("causales_rechazo"),
    anexos_obligatorios: createMockCategory("anexos_obligatorios"),
    datos_procedimiento: createMockCategory("datos_procedimiento"),
  };

  return {
    id: "analysis-1",
    created_at: new Date().toISOString(),
    status: "analyzed",
    current_stage: "completed",
    current_version: {
      id: "v1",
      version_number: 1,
      extracted_data: categories,
      conflicts: {},
      created_at: new Date().toISOString(),
    },
    documents: [{ id: "doc-1", filename: "Pliego.pdf", is_primary: true, page_count: 12 }],
  };
}

describe("CategoryAccordion", () => {
  beforeEach(() => {
    sessionStorage.clear();
    useAccordionState.setState({ expandedCategories: [], hasInitialized: false });
  });

  test("T1: Categoría crítica sin revisar muestra borde índigo y badge CRÍTICA", () => {
    const category = createMockCategory("plazos_clave", { is_reviewed: false });

    render(<CategoryAccordion category={category} categoryId="plazos_clave" />);

    const header = screen.getByRole("button");
    const wrapper = header.closest("article");

    expect(wrapper).toHaveClass("border-l-highlight", "bg-highlight-light");
    expect(screen.getByText(/CRÍTICA/i)).toBeInTheDocument();
  });

  test("T2: Categoría revisada muestra borde verde y badge REVISADA", () => {
    const category = createMockCategory("garantias", { is_reviewed: true });

    render(<CategoryAccordion category={category} categoryId="garantias" />);

    const wrapper = screen.getByRole("button").closest("article");
    expect(wrapper).toHaveClass("border-l-success");
    expect(screen.getByText(/REVISADA/i)).toBeInTheDocument();
  });

  test("T3: Categoría con conflictos muestra borde rojo y contador", () => {
    const category = createMockCategory("requisitos_admisibilidad", { conflictCount: 2 });

    render(<CategoryAccordion category={category} categoryId="requisitos_admisibilidad" />);

    const wrapper = screen.getByRole("button").closest("article");
    expect(wrapper).toHaveClass("border-l-error");
    expect(screen.getByText("2 conflictos")).toHaveClass("bg-error-light", "text-error");
  });

  test("T4: Click en header expande y colapsa acordeón", async () => {
    const user = userEvent.setup();
    const category = createMockCategory("objeto_alcance");

    render(<CategoryAccordion category={category} categoryId="objeto_alcance" />);

    const header = screen.getByRole("button");
    expect(screen.queryByText(category.summary)).not.toBeInTheDocument();

    await user.click(header);
    expect(screen.getByText(category.summary)).toBeInTheDocument();

    await user.click(header);
    expect(screen.queryByText(category.summary)).not.toBeInTheDocument();
  });

  test("T5: Campos ordenados por severidad", async () => {
    const user = userEvent.setup();
    const fields: FieldItem[] = [
      createField("field1", { state: "extraido", confidence: 0.9 }),
      createField("field2", { state: "en_conflicto" }),
      createField("field3", { state: "no_encontrado" }),
      createField("field4", { state: "extraido", confidence: 0.5 }),
      createField("field5", { state: "extraido", confidence: 0.7 }),
    ];

    const category = createMockCategory("garantias", { items: fields });

    render(<CategoryAccordion category={category} categoryId="garantias" />);

    await user.click(screen.getByRole("button"));

    // field1 has high confidence (0.9) and needs no action, so it renders as a
    // compact FieldRow instead of a full FieldCard — the rest still need action.
    const fieldCards = screen.getAllByTestId("field-card");
    expect(fieldCards[0]).toHaveTextContent("field2");
    expect(fieldCards[1]).toHaveTextContent("field3");
    expect(fieldCards[2]).toHaveTextContent("field4");
    expect(fieldCards[3]).toHaveTextContent("field5");

    const fieldRows = screen.getAllByTestId("field-row");
    expect(fieldRows[0]).toHaveTextContent("field1");
  });

  test("T6: Header colapsado muestra contadores como badges", () => {
    const category = createMockCategory("plazos_clave", {
      extractedCount: 5,
      notFoundCount: 2,
      conflictCount: 1,
    });

    render(<CategoryAccordion category={category} categoryId="plazos_clave" />);

    expect(screen.getByText("5 extraídos")).toHaveClass("bg-success-light", "text-success");
    expect(screen.getByText("2 no encontrados")).toHaveClass("bg-warning-light", "text-warning");
    expect(screen.getByText("1 conflicto")).toHaveClass("bg-error-light", "text-error");
  });

  test("T6b: Categoría sin ningún campo no muestra badges de conteo vacíos", () => {
    const category = createMockCategory("plazos_clave", {
      extractedCount: 0,
      notFoundCount: 0,
      conflictCount: 0,
    });

    render(<CategoryAccordion category={category} categoryId="plazos_clave" />);

    expect(screen.queryByText(/extraídos/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/no encontrados/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/conflicto/i)).not.toBeInTheDocument();
  });

  test("T7: Categoría con extraction_status=failed muestra badge ERROR", () => {
    const category = createMockCategory("criterios_evaluacion", { extraction_status: "failed" });

    render(<CategoryAccordion category={category} categoryId="criterios_evaluacion" />);

    expect(screen.getByText("ERROR")).toBeInTheDocument();
  });

  test("T7b: Categoría con extraction_status=not_applicable muestra badge NO APLICA", () => {
    const category = createMockCategory("datos_procedimiento", { extraction_status: "not_applicable" });

    render(<CategoryAccordion category={category} categoryId="datos_procedimiento" />);

    expect(screen.getByText("NO APLICA")).toBeInTheDocument();
  });

  test("T7c: Categoría con extraction_status=not_found no cae en badge ERROR", () => {
    const category = createMockCategory("objeto_alcance", { extraction_status: "not_found" });

    render(<CategoryAccordion category={category} categoryId="objeto_alcance" />);

    expect(screen.getByText("SIN REVISAR")).toBeInTheDocument();
    expect(screen.queryByText("ERROR")).not.toBeInTheDocument();
  });

  test("T8: Cada categoría muestra su icono correcto", () => {
    const categories: CategoryId[] = [
      "objeto_alcance",
      "requisitos_admisibilidad",
      "garantias",
      "plazos_clave",
    ];

    categories.forEach((categoryId) => {
      const { container } = render(<CategoryAccordion category={createMockCategory(categoryId)} categoryId={categoryId} />);
      const icon = CATEGORY_ICONS[categoryId];
      expect(container.querySelector(`[data-icon=\"${icon.displayName ?? icon.name}\"]`)).toBeInTheDocument();
    });
  });

  test("T9: Persistencia de estado expandido en sessionStorage", async () => {
    const user = userEvent.setup();

    // "objeto_alcance" is not a critical category and has no conflicts in the
    // default mock, so it starts collapsed and this exercises a genuine manual
    // toggle (unlike a critical category, which auto-expands on first visit).
    const { unmount } = render(<CategoryList analysis={createMockAnalysis()} />);

    await user.click(screen.getByRole("button", { name: /Objeto y Alcance/i }));
    unmount();

    render(<CategoryList analysis={createMockAnalysis()} />);

    expect(screen.getByText(/Resumen de objeto_alcance/i)).toBeInTheDocument();
  });

  test("T9b: Categorías críticas sin revisar o con conflictos se expanden solas la primera vez", () => {
    render(<CategoryList analysis={createMockAnalysis()} />);

    // plazos_clave/garantias/causales_rechazo are critical and unreviewed by default.
    expect(screen.getByText(/Resumen de plazos/i)).toBeInTheDocument();
    expect(screen.getByText(/Resumen de garantías/i)).toBeInTheDocument();
    // objeto_alcance is not critical and has no conflicts, so it stays collapsed.
    expect(screen.queryByText(/Resumen de objeto_alcance/i)).not.toBeInTheDocument();
  });

  test("T9c: El auto-expandido inicial no vuelve a pisar los cambios manuales del usuario", async () => {
    const user = userEvent.setup();

    const { unmount } = render(<CategoryList analysis={createMockAnalysis()} />);
    await user.click(screen.getByRole("button", { name: /Plazos Clave/i }));
    expect(screen.queryByText(/Resumen de plazos/i)).not.toBeInTheDocument();
    unmount();

    render(<CategoryList analysis={createMockAnalysis()} />);
    expect(screen.queryByText(/Resumen de plazos/i)).not.toBeInTheDocument();
  });

  test("T10: Acordeón es accesible por teclado y aria", () => {
    const category = createMockCategory("objeto_alcance");

    render(<CategoryAccordion category={category} categoryId="objeto_alcance" />);

    const header = screen.getByRole("button");
    expect(header).toHaveAttribute("aria-expanded", "false");
    expect(header).toHaveAttribute("aria-controls", "category-content-objeto_alcance");
  });
});
