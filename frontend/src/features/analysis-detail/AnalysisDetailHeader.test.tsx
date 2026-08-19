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
  denominacion?: string;
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
    overrides?.denominacion ||
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
        ...(overrides.denominacion
          ? [
              {
                field_name: "Denominación",
                field_value: overrides.denominacion,
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
  // FIX (2026-08-13): antes el H1 mostraba directamente el campo "Objeto"
  // (una síntesis de 2-4 oraciones), lo que producía títulos larguísimos.
  // Estos tests se actualizaron para reflejar el título corto nuevo
  // (armado desde tipo de procedimiento + número, ver `buildShortTitle`).
  //
  // FIX (2026-08-13, seguimiento): el header mostraba además el objeto
  // completo como descripción aparte -- se sacó por ser información
  // duplicada (la categoría "Objeto y Alcance" ya tiene su propia tarjeta
  // más abajo en la página). El header ya nunca renderiza el campo "objeto",
  // así que estos tests solo verifican título/subtítulo/presupuesto.
  test("el titulo (H1) es corto -- tipo de procedimiento + numero, con dedupe si el numero ya incluye el tipo", () => {
    const analysis = createAnalysis({
      objeto: "La contratación del servicio de limpieza integral de los edificios municipales de Villa Nueva",
      organismo: "Municipalidad de Villa Nueva",
      expediente: "0100-EXP-2026",
      tipoProcedimiento: "Contratación Directa",
      procedimiento: "Contratación Directa N° 014/2026",
      presupuestoOficial: "$ 3.850.000",
    });

    render(<AnalysisDetailHeader analysis={analysis} />);

    // El campo "Procedimiento" ya incluye el tipo -- el título usa ese valor
    // tal cual en vez de duplicar "Contratación Directa" dos veces.
    const title = screen.getByText("Contratación Directa N° 014/2026");
    expect(title.tagName).toBe("H1");

    expect(screen.getByText("Municipalidad de Villa Nueva · 0100-EXP-2026")).toBeInTheDocument();
    expect(screen.getByText("Presupuesto oficial: $ 3.850.000")).toBeInTheDocument();

    // El objeto ya no se muestra en el header -- queda solo en la tarjeta de
    // "Objeto y Alcance", más abajo en la página (fuera de este componente).
    expect(
      screen.queryByText(
        "La contratación del servicio de limpieza integral de los edificios municipales de Villa Nueva",
      ),
    ).not.toBeInTheDocument();
  });

  test("titulo combina tipo + numero cuando el numero NO repite el tipo", () => {
    const analysis = createAnalysis({
      tipoProcedimiento: "Licitación Privada",
      procedimiento: "45/2026",
      organismo: "Municipalidad de Rosario",
    });

    render(<AnalysisDetailHeader analysis={analysis} />);

    const title = screen.getByText("Licitación Privada — 45/2026");
    expect(title.tagName).toBe("H1");
  });

  // Caso real detectado (2026-08-13): un pliego-plantilla nombra el tipo de
  // procedimiento ("Licitación Privada") pero todavía no tiene un número
  // asignado. Antes de este fix el backend podía alucinar un
  // `numero_procedimiento` roto (ej. "Licitación Privada N° para", cortado a
  // mitad de oración) -- la corrección de fondo es a nivel de prompt (ver
  // `identificacion_procedimiento.txt`, que ahora instruye a NO emitir el
  // ítem cuando no hay número real). Este test cubre el caso límite sin
  // denominación tampoco: el título cae al tipo de procedimiento solo, sin
  // ítem roto ni "N°" inventado.
  test("con tipo de procedimiento pero sin numero ni denominacion, el titulo cae al tipo solo", () => {
    const analysis = createAnalysis({
      tipoProcedimiento: "Licitación Privada",
      organismo: "Municipalidad de Rosario",
      presupuestoOficial: "$ X",
    });

    render(<AnalysisDetailHeader analysis={analysis} />);

    const title = screen.getByText("Licitación Privada");
    expect(title.tagName).toBe("H1");
    expect(screen.getByText("Municipalidad de Rosario")).toBeInTheDocument();
    expect(screen.getByText("Presupuesto oficial: $ X")).toBeInTheDocument();
    // Nada de "N°" inventado ni texto cortado a mitad de oración.
    expect(screen.queryByText(/N°/)).not.toBeInTheDocument();
  });

  // Mismo caso pero con `denominacion` disponible (el título corto que el
  // pliego trae en la carátula, o que el LLM arma a partir del objeto cuando
  // no hay uno propio -- ver sección 7 de `identificacion_procedimiento.txt`).
  // Este es el caso real que reportó el usuario: sin esto, el título quedaba
  // en "Licitación Privada" a secas, sin decir qué se licita.
  test("con tipo de procedimiento y denominacion (sin numero), el titulo combina ambos", () => {
    const analysis = createAnalysis({
      tipoProcedimiento: "Licitación Privada",
      denominacion: "Adquisición de Servidores de aplicaciones y base de datos",
      organismo: "Municipalidad de Rosario",
      presupuestoOficial: "$ X",
    });

    render(<AnalysisDetailHeader analysis={analysis} />);

    const title = screen.getByText(
      "Licitación Privada — Adquisición de Servidores de aplicaciones y base de datos",
    );
    expect(title.tagName).toBe("H1");
    expect(screen.getByText("Municipalidad de Rosario")).toBeInTheDocument();
    expect(screen.getByText("Presupuesto oficial: $ X")).toBeInTheDocument();
    expect(screen.queryByText(/N°/)).not.toBeInTheDocument();
  });

  test("sin tipo/numero de procedimiento, el titulo cae a organismo -- nunca al objeto largo", () => {
    const analysis = createAnalysis({
      objeto: "Descripción larga del objeto que no debe usarse como título del análisis",
      organismo: "Municipalidad de Villa Nueva",
    });

    render(<AnalysisDetailHeader analysis={analysis} />);

    const title = screen.getByText("Municipalidad de Villa Nueva");
    expect(title.tagName).toBe("H1");
    expect(
      screen.queryByText("Descripción larga del objeto que no debe usarse como título del análisis"),
    ).not.toBeInTheDocument();
  });

  test("sin ningun dato de identificacion ni objeto, cae al nombre del archivo y no muestra un subtítulo vacío", () => {
    const analysis = createAnalysis({});

    const { container } = render(<AnalysisDetailHeader analysis={analysis} />);

    // El fixture siempre trae un documento primario -- sin tipo/numero/
    // organismo/analysis_name, el título cae al filename ("pliego.pdf").
    // El breadcrumb usa el mismo fallback, así que el texto aparece dos
    // veces en la página -- se busca puntualmente el H1.
    const title = container.querySelector("h1");
    expect(title).not.toBeNull();
    expect(title?.textContent).toBe("pliego.pdf");
    expect(title?.nextElementSibling).toBeNull();
  });
});
