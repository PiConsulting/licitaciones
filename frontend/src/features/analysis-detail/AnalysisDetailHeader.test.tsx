import { render, screen } from "@testing-library/react";

import { AnalysisDetailHeader } from "./AnalysisDetailHeader";
import type { AnalysisDetail, CategoryData, CategoryId } from "./types";

const EMPTY_CATEGORY: CategoryData = {
  items: [],
  confidence: 0,
  source_references: [],
  extraction_status: "not_found",
  summary: "",
  is_reviewed: false,
};

function createAnalysis(overrides?: {
  objeto?: string;
  organismo?: string;
  expediente?: string;
  procedimiento?: string;
  tipoProcedimiento?: string;
  presupuestoOficial?: string;
}): AnalysisDetail {
  const extracted_data = {
    objeto_alcance: EMPTY_CATEGORY,
    requisitos_admisibilidad: EMPTY_CATEGORY,
    garantias: EMPTY_CATEGORY,
    plazos_clave: EMPTY_CATEGORY,
    criterios_evaluacion: EMPTY_CATEGORY,
    causales_rechazo: EMPTY_CATEGORY,
    anexos_obligatorios: EMPTY_CATEGORY,
    datos_procedimiento: EMPTY_CATEGORY,
  } as Record<CategoryId, CategoryData>;

  if (overrides?.objeto) {
    extracted_data.objeto_alcance = {
      ...EMPTY_CATEGORY,
      extraction_status: "success",
      items: [
        {
          field_name: "Objeto",
          field_value: overrides.objeto,
          field_state: "extraido",
          confidence: 0.9,
          citations: [],
        },
      ],
    };
  }

  if (
    overrides?.organismo ||
    overrides?.expediente ||
    overrides?.procedimiento ||
    overrides?.tipoProcedimiento ||
    overrides?.presupuestoOficial
  ) {
    extracted_data.datos_procedimiento = {
      ...EMPTY_CATEGORY,
      extraction_status: "success",
      items: [
        ...(overrides.organismo
          ? [
              {
                field_name: "Organismo convocante",
                field_value: overrides.organismo,
                field_state: "extraido" as const,
                confidence: 0.9,
                citations: [],
              },
            ]
          : []),
        ...(overrides.expediente
          ? [
              {
                field_name: "Expediente",
                field_value: overrides.expediente,
                field_state: "extraido" as const,
                confidence: 0.9,
                citations: [],
              },
            ]
          : []),
        ...(overrides.tipoProcedimiento
          ? [
              {
                field_name: "Tipo de procedimiento",
                field_value: overrides.tipoProcedimiento,
                field_state: "extraido" as const,
                confidence: 0.9,
                citations: [],
              },
            ]
          : []),
        ...(overrides.procedimiento
          ? [
              {
                field_name: "Procedimiento",
                field_value: overrides.procedimiento,
                field_state: "extraido" as const,
                confidence: 0.9,
                citations: [],
              },
            ]
          : []),
        ...(overrides.presupuestoOficial
          ? [
              {
                field_name: "Presupuesto oficial",
                field_value: overrides.presupuestoOficial,
                field_state: "extraido" as const,
                confidence: 0.9,
                citations: [],
              },
            ]
          : []),
      ],
    };
  }

  return {
    id: "analysis-1",
    created_at: "2026-08-05T00:00:00Z",
    status: "analyzed",
    current_stage: "completed",
    current_version: {
      id: "v1",
      version_number: 1,
      extracted_data,
      conflicts: {},
      created_at: "2026-08-05T00:00:00Z",
    },
    documents: [{ id: "doc-1", filename: "pliego.pdf", is_primary: true, page_count: 10 }],
  };
}

describe("AnalysisDetailHeader", () => {
  test("muestra el organismo convocante y el expediente como subtítulo", () => {
    const analysis = createAnalysis({
      objeto: "La contratación del servicio de limpieza integral de los edificios municipales de Villa Nueva",
      organismo: "Municipalidad de Villa Nueva",
      expediente: "0100-EXP-2026",
      tipoProcedimiento: "Contratación Directa",
      procedimiento: "Contratación Directa N° 014/2026",
      presupuestoOficial: "$ 3.850.000",
    });

    render(<AnalysisDetailHeader analysis={analysis} />);

    expect(
      screen.getByText("La contratación del servicio de limpieza integral de los edificios municipales de Villa Nueva"),
    ).toBeInTheDocument();
    expect(screen.getByText("Municipalidad de Villa Nueva · 0100-EXP-2026")).toBeInTheDocument();
    expect(screen.getByText("Contratación Directa · Contratación Directa N° 014/2026")).toBeInTheDocument();
    expect(screen.getByText("Presupuesto oficial: $ 3.850.000")).toBeInTheDocument();
  });

  test("sin organismo extraído, no muestra un subtítulo vacío", () => {
    const analysis = createAnalysis({ objeto: "Objeto del pliego" });

    const { container } = render(<AnalysisDetailHeader analysis={analysis} />);

    const title = screen.getByText("Objeto del pliego");
    expect(title.tagName).toBe("H1");
    expect(container.querySelector("h1")?.nextElementSibling).toBeNull();
  });
});
