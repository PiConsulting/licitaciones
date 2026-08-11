import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { CategorySection } from "./CategorySection";
import type { CategoryData, CategoryId, CategoryNarrative, FieldItem } from "./types";
import { CATEGORY_ICONS } from "../../utils/categoryIcons";

function createField(
  field_name: string,
  options?: {
    state?: FieldItem["field_state"];
    confidence?: number;
    value?: string | null;
    citations?: FieldItem["citations"];
  },
): FieldItem {
  return {
    field_name,
    field_value: options?.value ?? field_name,
    field_state: options?.state ?? "extraido",
    confidence: options?.confidence ?? 0.9,
    citations:
      options?.citations ?? [
        {
          text: `Cita de ${field_name} con suficiente longitud como para ser clickeable`,
          page: 2,
          document_id: "doc-1",
          document_name: "Pliego.pdf",
        },
      ],
  };
}

function makeNarrative(text: string): CategoryNarrative {
  return {
    blocks: [{ type: "paragraph", text, confidence_level: "high", source_ids: [] }],
    sources: [],
  };
}

function createMockCategory(
  options?: {
    is_reviewed?: boolean;
    extraction_status?: CategoryData["extraction_status"];
    conflictCount?: number;
    extractedCount?: number;
    notFoundCount?: number;
    summary?: string;
    narrative?: CategoryNarrative;
    items?: FieldItem[];
  },
): CategoryData {
  if (options?.items) {
    return {
      items: options.items,
      confidence: 0.8,
      source_references: [],
      extraction_status: options.extraction_status ?? "success",
      summary: options.summary ?? "Resumen",
      is_reviewed: options.is_reviewed ?? false,
      narrative: options.narrative,
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
    source_references: [],
    extraction_status: options?.extraction_status ?? "success",
    summary: options?.summary ?? "Resumen",
    is_reviewed: options?.is_reviewed ?? false,
    narrative: options?.narrative,
  };
}

describe("CategorySection", () => {
  test("T1: Categoría crítica sin revisar muestra borde índigo y badge CRÍTICA", () => {
    const category = createMockCategory({ is_reviewed: false });

    render(<CategorySection category={category} categoryId="garantias" />);

    const wrapper = document.getElementById("category-garantias");
    expect(wrapper).toHaveClass("border-l-highlight");
    expect(screen.getByText(/CRÍTICA/i)).toBeInTheDocument();
  });

  test("T2: Categoría revisada muestra borde verde y badge REVISADA", () => {
    const category = createMockCategory({ is_reviewed: true });

    render(<CategorySection category={category} categoryId="garantias" />);

    const wrapper = document.getElementById("category-garantias");
    expect(wrapper).toHaveClass("border-l-success");
    expect(screen.getByText(/REVISADA/i)).toBeInTheDocument();
  });

  test("T3: Categoría con conflictos muestra borde rojo y contador", () => {
    const category = createMockCategory({ conflictCount: 2 });

    render(<CategorySection category={category} categoryId="requisitos_admisibilidad" />);

    const wrapper = document.getElementById("category-requisitos_admisibilidad");
    expect(wrapper).toHaveClass("border-l-error");
    expect(screen.getByText("2 conflictos")).toHaveClass("bg-error-light", "text-error");
  });

  test("T4: La sección siempre muestra la narrativa del backend cuando está disponible", () => {
    const category = createMockCategory({ narrative: makeNarrative("Este pliego solicita una garantía del 5%.") });

    render(<CategorySection category={category} categoryId="objeto_alcance" />);

    expect(screen.getByText("Este pliego solicita una garantía del 5%.")).toBeInTheDocument();
  });

  test("T5: Nunca muestra field_name: field_value crudo — solo la respuesta en bloques", () => {
    const fields: FieldItem[] = [
      createField("field1", { state: "extraido", confidence: 0.9, value: "Valor uno" }),
      createField("field2", { state: "en_conflicto" }),
      createField("field3", { state: "no_encontrado" }),
    ];

    const category = createMockCategory({ items: fields });

    render(<CategorySection category={category} categoryId="garantias" />);

    expect(screen.queryByTestId("field-card")).not.toBeInTheDocument();
    expect(screen.queryByTestId("field-row")).not.toBeInTheDocument();
    expect(screen.getByTestId("narrative-bullet-list")).toBeInTheDocument();
  });

  test("T5b: Muestra bullet_list cuando hay más de un ítem", () => {
    const fields: FieldItem[] = [
      createField("criterio_1", { value: "Precio total de la oferta" }),
      createField("criterio_2", { value: "Experiencia en contratos similares" }),
      createField("criterio_3", { value: "Plan de trabajo propuesto" }),
    ];
    const category = createMockCategory({ items: fields });

    render(<CategorySection category={category} categoryId="criterios_evaluacion" />);

    const bullets = screen.getByTestId("narrative-bullet-list");
    expect(bullets).toBeInTheDocument();
    expect(screen.getAllByTestId("narrative-bullet-item")).toHaveLength(3);
  });

  test("T5c: Muestra fallback controlado cuando no hay extracción útil", () => {
    const category = createMockCategory({
      items: [createField("garantia_anticipo", { state: "no_encontrado", value: null })],
    });

    render(<CategorySection category={category} categoryId="garantias" />);

    expect(screen.getByText(/No se encontró información sobre garantías/i)).toBeInTheDocument();
    expect(screen.queryByTestId("narrative-bullet-list")).not.toBeInTheDocument();
  });

  test("T5d: La fuente citada por un ítem aparece en Fuentes verificables", () => {
    const category = createMockCategory({
      items: [
        createField("objeto", {
          value: "Servicio de mantenimiento preventivo",
          citations: [
            {
              text: "El objeto es la contratación de mantenimiento preventivo.",
              page: 8,
              document_id: "doc-1",
              document_name: "Pliego.pdf",
            },
          ],
        }),
      ],
    });

    render(<CategorySection category={category} categoryId="objeto_alcance" />);

    expect(screen.getByRole("button", { name: /Pliego\.pdf · pág\. 8/i })).toBeInTheDocument();
  });

  test("T6: Muestra contadores como badges", () => {
    const category = createMockCategory({
      extractedCount: 5,
      notFoundCount: 2,
      conflictCount: 1,
    });

    render(<CategorySection category={category} categoryId="requisitos_admisibilidad" />);

    expect(screen.getByText("5 extraídos")).toHaveClass("bg-success-light", "text-success");
    expect(screen.getByText("2 no encontrados")).toHaveClass("bg-warning-light", "text-warning");
    expect(screen.getByText("1 conflicto")).toHaveClass("bg-error-light", "text-error");
  });

  test("T6b: Categoría sin ningún campo no muestra badges de conteo vacíos", () => {
    const category = createMockCategory({
      extractedCount: 0,
      notFoundCount: 0,
      conflictCount: 0,
    });

    render(<CategorySection category={category} categoryId="requisitos_admisibilidad" />);

    expect(screen.queryByText(/extraídos/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/no encontrados/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/conflicto/i)).not.toBeInTheDocument();
  });

  test("T7: Categoría con extraction_status=failed muestra badge ERROR", () => {
    const category = createMockCategory({ extraction_status: "failed" });

    render(<CategorySection category={category} categoryId="criterios_evaluacion" />);

    expect(screen.getByText("ERROR")).toBeInTheDocument();
  });

  test("T7b: Categoría con extraction_status=not_applicable muestra badge NO APLICA", () => {
    const category = createMockCategory({
      extraction_status: "not_applicable",
      items: [createField("x", { state: "no_aplica", confidence: 0.8, value: "No exigido" })],
    });

    render(<CategorySection category={category} categoryId="anexos_obligatorios" />);

    expect(screen.getByText("NO APLICA")).toBeInTheDocument();
    expect(screen.getByText("1 no aplica")).toBeInTheDocument();
  });

  test("T7d: Si hay extraídos, oculta contador no aplica para evitar mezcla confusa", () => {
    const category = createMockCategory({
      items: [
        createField("extraido-1", { state: "extraido", value: "Dato válido" }),
        createField("no-aplica-1", { state: "no_aplica", value: "No exigido" }),
      ],
      extraction_status: "success",
    });

    render(<CategorySection category={category} categoryId="garantias" />);

    expect(screen.queryByText(/^1 no aplica$/i)).not.toBeInTheDocument();
    expect(screen.getByText("1 extraídos")).toBeInTheDocument();
  });

  test("T7c: Categoría con extraction_status=not_found no cae en badge ERROR y oculta SIN REVISAR", () => {
    const category = createMockCategory({ extraction_status: "not_found" });

    render(<CategorySection category={category} categoryId="objeto_alcance" />);

    expect(screen.queryByText("SIN REVISAR")).not.toBeInTheDocument();
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
      const { container } = render(<CategorySection category={createMockCategory()} categoryId={categoryId} />);
      const icon = CATEGORY_ICONS[categoryId];
      expect(container.querySelector(`[data-icon=\"${icon.displayName ?? icon.name}\"]`)).toBeInTheDocument();
    });
  });

  test("T9: Muestra fuentes clickeables por categoría y dispara navegación con cita exacta", async () => {
    const user = userEvent.setup();
    const onViewSource = vi.fn();
    const category = createMockCategory({
      items: [
        createField("objeto", {
          value: "Servicio integral",
          citations: [
            {
              text: "El objeto de la contratación es el servicio integral.",
              page: 12,
              document_id: "doc-1",
              document_name: "Pliego Principal.pdf",
            },
          ],
        }),
      ],
    });

    render(<CategorySection category={category} categoryId="objeto_alcance" onViewSource={onViewSource} />);

    const sourceButton = screen.getByRole("button", { name: /Pliego Principal.pdf · pág. 12/i });
    await user.click(sourceButton);

    expect(onViewSource).toHaveBeenCalledWith(
      expect.objectContaining({
        citation: expect.objectContaining({
          document_id: "doc-1",
          page: 12,
          text: "El objeto de la contratación es el servicio integral.",
        }),
      }),
    );
  });

  test("T10: Sin citas muestra aviso de no evidencia y evita estado revisada automática", () => {
    const category = createMockCategory({
      is_reviewed: true,
      items: [
        createField("campo_sin_cita", {
          value: "Dato sin cita",
          citations: [],
        }),
      ],
    });

    render(<CategorySection category={category} categoryId="garantias" />);

    expect(screen.getByTestId("category-sources-empty")).toBeInTheDocument();
    expect(screen.queryByText(/^REVISADA$/i)).not.toBeInTheDocument();
    expect(screen.getByText(/CRÍTICA/i)).toBeInTheDocument();
  });

  test("T11: Plazos Clave renderiza la línea de tiempo en vez de la respuesta narrativa", () => {
    const category = createMockCategory({
      items: [
        {
          ...createField("apertura", { value: "12/09/2026" }),
          raw: { fecha: "2026-09-12", hora: null, expresion_relativa: null, texto_original: "12/09/2026", lugar: null },
        },
      ],
    });

    render(<CategorySection category={category} categoryId="plazos_clave" />);

    expect(screen.getByTestId("plazos-timeline")).toBeInTheDocument();
    expect(screen.queryByTestId("narrative-blocks")).not.toBeInTheDocument();
  });
});
