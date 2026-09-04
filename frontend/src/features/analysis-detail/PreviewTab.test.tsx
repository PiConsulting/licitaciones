import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PreviewTab } from "./PreviewTab";
import type { AnalysisDetail, CategoryData } from "./types";

function makeCategoryData(items: CategoryData["items"]): CategoryData {
  return {
    items,
    confidence: items.length > 0 ? 0.8 : 0,
    source_references: [],
    extraction_status: "success",
    summary: "",
    is_reviewed: false,
  };
}

function makeAnalysis(options?: { previewCriterios?: CategoryData }): AnalysisDetail {
  return {
    id: "analysis-1",
    created_at: new Date().toISOString(),
    status: "analyzed",
    current_stage: "completed",
    current_version: {
      id: "v1",
      version_number: 1,
      extracted_data: {
        objeto_alcance: makeCategoryData([
          {
            field_name: "Objeto",
            field_value: "Servicio de mantenimiento integral",
            field_state: "extraido",
            confidence: 0.9,
            citations: [
              {
                text: "Se contrata servicio de mantenimiento integral.",
                page: 3,
                document_id: "doc-1",
                document_name: "Pliego.pdf",
              },
            ],
          },
        ]),
        riesgos: makeCategoryData([]),
        requisitos_admisibilidad: makeCategoryData([]),
        garantias: makeCategoryData([]),
        plazos_clave: makeCategoryData([]),
        criterios_evaluacion: makeCategoryData([]),
        causales_rechazo: makeCategoryData([]),
        anexos_obligatorios: makeCategoryData([]),
        datos_procedimiento: makeCategoryData([]),
        preview_criterios: options?.previewCriterios,
      },
      conflicts: {},
      created_at: new Date().toISOString(),
    },
    documents: [{ id: "doc-1", filename: "Pliego.pdf", is_primary: true, page_count: 12 }],
    tracking: null,
  };
}

function makeLegacyAnalysisWithoutPreview(): AnalysisDetail {
  const analysis = makeAnalysis();
  analysis.current_version.extracted_data.objeto_alcance = makeCategoryData([]);
  delete (analysis.current_version.extracted_data as Record<string, unknown>).preview_criterios;
  return analysis;
}

describe("PreviewTab", () => {
  test("muestra estado vacío y nota legacy cuando faltan datos de preview en análisis pre-incremento", () => {
    const analysis = makeLegacyAnalysisWithoutPreview();

    render(<PreviewTab analysis={analysis} />);

    expect(screen.getByTestId("preview-tab-empty")).toBeInTheDocument();
    expect(screen.getByTestId("preview-tab-legacy-note")).toBeInTheDocument();
  });

  test("renderiza vista unificada de objeto y alcance + criterios de preview en un solo contenedor, sin cajas separadas", () => {
    const analysis = makeAnalysis({
      previewCriterios: makeCategoryData([
        {
          field_name: "Mantenimiento de oferta",
          field_value: "60 días",
          field_state: "extraido",
          confidence: 0.8,
          citations: [],
        },
      ]),
    });

    render(<PreviewTab analysis={analysis} />);

    expect(screen.getByTestId("preview-tab-content")).toBeInTheDocument();
    // Un único contenedor "Respuesta" (NarrativeBlocks se renderiza una sola
    // vez), no dos cajas separadas para objeto/alcance y criterios.
    expect(screen.getAllByTestId("narrative-blocks")).toHaveLength(1);
    expect(screen.queryByTestId("preview-criteria-section")).not.toBeInTheDocument();

    expect(screen.getByTestId("preview-tab-content")).toHaveTextContent(
      "Objeto: Servicio de mantenimiento integral.",
    );
    expect(screen.getByTestId("preview-tab-content")).toHaveTextContent(
      "Mantenimiento de oferta: 60 días.",
    );
    expect(screen.queryByText("Objeto:", { selector: "strong" })).not.toBeInTheDocument();
    expect(screen.getByText("Mantenimiento de oferta:").tagName).toBe("STRONG");
    expect(screen.queryByText("Objeto y Alcance")).not.toBeInTheDocument();
  });

  test("cuando un criterio está no_encontrado mantiene el título del ítem y lo explicita", () => {
    const analysis = makeAnalysis({
      previewCriterios: makeCategoryData([
        {
          field_name: "Penalidades específicas",
          field_value: null,
          field_state: "no_encontrado",
          confidence: 0.4,
          citations: [],
        },
      ]),
    });

    render(<PreviewTab analysis={analysis} />);

    // El item no desaparece: conserva su título y explica que no se encontró.
    expect(screen.getByTestId("preview-tab-content")).toHaveTextContent(
      "penalidades específicas",
    );
    expect(screen.getByTestId("preview-tab-content")).toHaveTextContent(
      "No se encontró información sobre penalidades específicas",
    );
    expect(screen.queryByTestId("preview-criteria-section")).not.toBeInTheDocument();
  });

  test("usa la narrativa sintetizada del backend en vez de reconstruir desde los ítems crudos", () => {
    const analysis = makeAnalysis({
      previewCriterios: makeCategoryData([
        {
          field_name: "Moneda",
          field_value: "Dólares estadounidenses",
          field_state: "extraido",
          confidence: 0.8,
          citations: [],
        },
      ]),
    });
    // Backend ya sintetizó objeto_alcance: un resumen corto, sin el prefijo
    // "Objeto:" que arma el fallback local.
    analysis.current_version.extracted_data.objeto_alcance.narrative = {
      blocks: [
        {
          type: "paragraph",
          text: "Contratación de un servicio de mantenimiento integral de infraestructura.",
          confidence_level: "high",
          source_ids: [],
        },
      ],
      sources: [],
    };

    render(<PreviewTab analysis={analysis} />);

    expect(screen.getByTestId("preview-tab-content")).toHaveTextContent(
      "Contratación de un servicio de mantenimiento integral de infraestructura.",
    );
    // El fallback local antepone la etiqueta cruda del campo ("Objeto:") en
    // negrita; la narrativa real del backend no la tiene.
    expect(screen.queryByText("Objeto:")).not.toBeInTheDocument();
  });

  test("permite ver fuente por ítem cuando hay evidencia", async () => {
    const user = userEvent.setup();
    const onViewSource = vi.fn();
    const analysis = makeAnalysis({
      previewCriterios: makeCategoryData([
        {
          field_name: "Anticipo financiero",
          field_value: "10% contra póliza",
          field_state: "extraido",
          confidence: 0.8,
          citations: [
            {
              text: "Se admite anticipo del 10% contra póliza.",
              page: 7,
              document_id: "doc-1",
              document_name: "Pliego.pdf",
            },
          ],
        },
      ]),
    });

    render(<PreviewTab analysis={analysis} onViewSource={onViewSource} />);

    await user.click(screen.getByRole("button", { name: /Ver fuente en el pliego \(pág\. 7\)/i }));

    expect(onViewSource).toHaveBeenCalledTimes(1);
    expect(onViewSource).toHaveBeenCalledWith(
      expect.objectContaining({
        citation: expect.objectContaining({ document_id: "doc-1", page: 7 }),
      }),
    );
  });

  test("normaliza etiquetas y fuerza el orden canónico de preview incluso con narrativa del backend", () => {
    const analysis = makeAnalysis({
      previewCriterios: makeCategoryData([
        {
          field_name: "Costos logísticos",
          field_value: "A cargo del proveedor",
          field_state: "extraido",
          confidence: 0.8,
          citations: [],
        },
        {
          field_name: "Mantenimiento de oferta",
          field_value: "60 días corridos",
          field_state: "extraido",
          confidence: 0.8,
          citations: [],
        },
      ]),
    });

    analysis.current_version.extracted_data.preview_criterios = {
      ...analysis.current_version.extracted_data.preview_criterios,
      narrative: {
        blocks: [
          {
            type: "bullet_list",
            items: [
              {
                text: "Moneda: no se encontró información sobre este criterio en el pliego.",
                confidence_level: "low",
                source_ids: [],
              },
              {
                text: "Mantenimiento de oferta: 60 días corridos.",
                confidence_level: "high",
                source_ids: [],
              },
              {
                text: "Forma de pago: transferencia bancaria a 30 días.",
                confidence_level: "high",
                source_ids: [],
              },
              {
                text: "Costos logísticos: a cargo del proveedor.",
                confidence_level: "high",
                source_ids: [],
              },
              {
                text: "Multas y penalidades: no se encontró información sobre este criterio en el pliego.",
                confidence_level: "low",
                source_ids: [],
              },
            ],
          },
        ],
        sources: [],
      },
    };

    render(<PreviewTab analysis={analysis} />);

    const rendered = screen.getByTestId("preview-tab-content").textContent ?? "";
    const idxMantenimiento = rendered.indexOf("Mantenimiento de oferta:");
    const idxPago = rendered.indexOf("Forma de pago:");
    const idxMoneda = rendered.indexOf("Licitación en pesos o dólares:");
    const idxMultas = rendered.indexOf("Multas o penalidades:");
    const idxCostos = rendered.indexOf("Responsabilidad por costos logísticos o de instalación:");

    expect(idxMantenimiento).toBeGreaterThanOrEqual(0);
    expect(idxPago).toBeGreaterThan(idxMantenimiento);
    expect(idxMoneda).toBeGreaterThan(idxPago);
    expect(idxMultas).toBeGreaterThan(idxMoneda);
    expect(idxCostos).toBeGreaterThan(idxMultas);
    expect(rendered).not.toContain("Costos logísticos: a cargo del proveedor.");
    expect(rendered).toContain("Licitación en pesos o dólares:");
    expect(rendered).toContain("Multas o penalidades:");
    expect(rendered).toContain("Responsabilidad por costos logísticos o de instalación:");
  });

  test("reordena en el orden canónico cuando la narrativa llega con aliases de backend", () => {
    const analysis = makeAnalysis({
      previewCriterios: makeCategoryData([]),
    });

    analysis.current_version.extracted_data.preview_criterios = {
      ...analysis.current_version.extracted_data.preview_criterios,
      items: [
        {
          field_name: "Tiempo de entrega",
          field_value: "No se encontró información",
          field_state: "no_encontrado",
          confidence: 0.4,
          citations: [],
        },
      ],
      narrative: {
        blocks: [
          {
            type: "bullet_list",
            items: [
              {
                text: "Tiempo de entrega: no se encontró información específica sobre este criterio en los ítems recibidos.",
                confidence_level: "low",
                source_ids: [],
              },
              {
                text: "Forma de pago: el equipamiento se facturará contra su recepción definitiva y conformidad técnica.",
                confidence_level: "high",
                source_ids: [],
              },
              {
                text: "Tipo de cambio: las diferencias de cambio se toman entre el día anterior al pago y la fecha de emisión de la factura.",
                confidence_level: "high",
                source_ids: [],
              },
              {
                text: "Multas o penalidades: hay riesgo de sanciones por atrasos en la ejecución y en la atención de fallas, con penalidades económicas relevantes.",
                confidence_level: "high",
                source_ids: [],
              },
              {
                text: "Anticipo financiero requerido: no se encontró información sobre este criterio en los ítems recibidos.",
                confidence_level: "low",
                source_ids: [],
              },
              {
                text: "Requisitos técnicos o certificaciones excluyentes: no se encontró información específica sobre este criterio en los ítems recibidos.",
                confidence_level: "low",
                source_ids: [],
              },
              {
                text: "Responsabilidad por costos logísticos o de instalación: durante la instalación, calibración o puesta en marcha del software, todos los gastos quedan a cargo de la contratista.",
                confidence_level: "high",
                source_ids: [],
              },
              {
                text: "Moneda de cotización: los bienes y servicios nacionales deben cotizarse en pesos; los importados pueden cotizarse en pesos o en dólares estadounidenses.",
                confidence_level: "high",
                source_ids: [],
              },
              {
                text: "Garantías: el pliego remite a la garantía de mantenimiento de oferta y a la de fiel cumplimiento; además, la garantía de oferta se integra en pesos o en dólares según la moneda cotizada.",
                confidence_level: "high",
                source_ids: [],
              },
              {
                text: "Mantenimiento de la oferta: la oferta debe mantenerse vigente por el plazo indicado en el pliego y puede ser aceptada dentro de ese período.",
                confidence_level: "high",
                source_ids: [],
              },
            ],
          },
        ],
        sources: [],
      },
    };

    render(<PreviewTab analysis={analysis} />);

    const rendered = screen.getByTestId("preview-tab-content").textContent ?? "";
    const idxMantenimiento = rendered.indexOf("Mantenimiento de oferta:");
    const idxEntrega = rendered.indexOf("Tiempo de entrega:");
    const idxPago = rendered.indexOf("Forma de pago:");
    const idxMoneda = rendered.indexOf("Licitación en pesos o dólares:");
    const idxTipoCambio = rendered.indexOf("Tipo de cambio:");
    const idxGarantias = rendered.indexOf("Garantías o cauciones:");
    const idxMultas = rendered.indexOf("Multas o penalidades:");
    const idxAnticipo = rendered.indexOf("Anticipo financiero requerido:");
    const idxRequisitos = rendered.indexOf("Requisitos técnicos o certificaciones excluyentes:");
    const idxResponsabilidad = rendered.indexOf("Responsabilidad por costos logísticos o de instalación:");

    expect(idxMantenimiento).toBeGreaterThanOrEqual(0);
    expect(idxEntrega).toBeGreaterThan(idxMantenimiento);
    expect(idxPago).toBeGreaterThan(idxEntrega);
    expect(idxMoneda).toBeGreaterThan(idxPago);
    expect(idxTipoCambio).toBeGreaterThan(idxMoneda);
    expect(idxGarantias).toBeGreaterThan(idxTipoCambio);
    expect(idxMultas).toBeGreaterThan(idxGarantias);
    expect(idxAnticipo).toBeGreaterThan(idxMultas);
    expect(idxRequisitos).toBeGreaterThan(idxAnticipo);
    expect(idxResponsabilidad).toBeGreaterThan(idxRequisitos);
  });

  test("no pone en negrita párrafos de objeto y alcance con dos puntos", () => {
    const analysis = makeAnalysis({
      previewCriterios: makeCategoryData([
        {
          field_name: "Tiempo de entrega",
          field_value: "45 días",
          field_state: "extraido",
          confidence: 0.8,
          citations: [],
        },
      ]),
    });

    analysis.current_version.extracted_data.objeto_alcance.narrative = {
      blocks: [
        {
          type: "paragraph",
          text: "La licitación es para la adquisición de servidores de aplicaciones, de base de datos y de archivos. El objeto se divide en 3 ítems: 4 servidores de aplicaciones tipo XEN, 4 servidores de base de datos y 4 LCD KVM Switch.",
          confidence_level: "high",
          source_ids: [],
        },
      ],
      sources: [],
    };

    render(<PreviewTab analysis={analysis} />);

    expect(
      screen.getByText(
        "La licitación es para la adquisición de servidores de aplicaciones, de base de datos y de archivos. El objeto se divide en 3 ítems: 4 servidores de aplicaciones tipo XEN, 4 servidores de base de datos y 4 LCD KVM Switch.",
      ),
    ).toBeInTheDocument();

    expect(
      screen.queryByText(
        "La licitación es para la adquisición de servidores de aplicaciones, de base de datos y de archivos. El objeto se divide en 3 ítems:",
        { selector: "strong" },
      ),
    ).not.toBeInTheDocument();
  });
});
