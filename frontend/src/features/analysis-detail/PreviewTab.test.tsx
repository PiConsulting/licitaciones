import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { within } from "@testing-library/dom";

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

  test("renderiza 10 cards con título canónico, resumen y detalle siempre visibles", () => {
    const analysis = makeAnalysis({
      previewCriterios: makeCategoryData([]),
    });
    analysis.current_version.extracted_data.preview_criterios = {
      ...analysis.current_version.extracted_data.preview_criterios,
      narrative: {
        blocks: [
          {
            type: "bullet_list",
            items: [
              { text: "Mantenimiento de oferta: 60 días", resumen: "60 días", confidence_level: "high", source_ids: [] },
              { text: "Tiempo de entrega: 45 días", resumen: "45 días", confidence_level: "high", source_ids: [] },
              { text: "Forma de pago: Transferencia", resumen: "Transferencia", confidence_level: "high", source_ids: [] },
              { text: "Licitación en pesos o dólares: Pesos", resumen: "Pesos", confidence_level: "high", source_ids: [] },
              { text: "Tipo de cambio: BNA vendedor", resumen: "BNA vendedor", confidence_level: "high", source_ids: [] },
              { text: "Garantías o cauciones: 1%", resumen: "1%", confidence_level: "high", source_ids: [] },
              { text: "Multas o penalidades: Sí", resumen: "Sí", confidence_level: "high", source_ids: [] },
              { text: "Anticipo financiero requerido: No", resumen: "No", confidence_level: "high", source_ids: [] },
              { text: "Requisitos técnicos o certificaciones excluyentes: ISO 9001", resumen: "ISO 9001", confidence_level: "high", source_ids: [] },
              {
                text: "Responsabilidad por costos logísticos o de instalación: Proveedor",
                resumen: "Proveedor",
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

    const cards = screen.getAllByTestId("preview-criterion-card");
    expect(cards).toHaveLength(10);
    expect(screen.queryByRole("button", { name: /Expandir detalle/i })).not.toBeInTheDocument();
    expect(screen.getByText("Mantenimiento de oferta")).toBeInTheDocument();
    expect(screen.getAllByText("60 días").length).toBeGreaterThan(0);
  });

  test("muestra el detalle de cada card sin necesidad de desplegarla", () => {
    const analysis = makeAnalysis({
      previewCriterios: makeCategoryData([]),
    });
    analysis.current_version.extracted_data.preview_criterios = {
      ...analysis.current_version.extracted_data.preview_criterios,
      narrative: {
        blocks: [
          {
            type: "bullet_list",
            items: [
              {
                text: "Mantenimiento de oferta: La oferta deberá mantenerse por 60 días corridos.",
                resumen: "60 días",
                confidence_level: "high",
                source_ids: [],
              },
              {
                text: "Forma de pago: Pago a 30 días contra entrega.",
                resumen: "30 días",
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

    const cards = screen.getAllByTestId("preview-criterion-card");
    expect(cards).toHaveLength(2);

    expect(within(cards[0]).getByTestId("preview-criterion-detail")).toHaveTextContent(
      "La oferta deberá mantenerse por 60 días corridos.",
    );
    expect(within(cards[0]).getByTestId("preview-criterion-detail")).not.toHaveTextContent(
      "Mantenimiento de oferta:",
    );
    expect(within(cards[1]).getByTestId("preview-criterion-detail")).toHaveTextContent(
      "Pago a 30 días contra entrega.",
    );
  });

  test("permite ver fuente desde una card cuando hay evidencia", async () => {
    const user = userEvent.setup();
    const onViewSource = vi.fn();
    const analysis = makeAnalysis({
      previewCriterios: makeCategoryData([]),
    });
    analysis.current_version.extracted_data.preview_criterios = {
      ...analysis.current_version.extracted_data.preview_criterios,
      narrative: {
        blocks: [
          {
            type: "bullet_list",
            items: [
              {
                text: "Anticipo financiero requerido: Se admite anticipo del 10% contra póliza.",
                resumen: "10%",
                confidence_level: "high",
                source_ids: [0],
              },
            ],
          },
        ],
        sources: [
          {
            id: 0,
            document_id: "doc-1",
            document_name: "Pliego.pdf",
            page: 7,
            text: "Se admite anticipo del 10% contra póliza.",
          },
        ],
      },
    };

    render(<PreviewTab analysis={analysis} onViewSource={onViewSource} />);

    const card = screen.getAllByTestId("preview-criterion-card")[0];
    await user.click(within(card).getAllByRole("button", { name: /Ver fuente en el pliego \(pág\. 7\)/i })[0]);

    expect(onViewSource).toHaveBeenCalledTimes(1);
    expect(onViewSource).toHaveBeenCalledWith(
      expect.objectContaining({
        citation: expect.objectContaining({
          document_id: "doc-1",
          page: 7,
          text: "Se admite anticipo del 10% contra póliza.",
          document_name: "Pliego.pdf",
        }),
        citations: [
          expect.objectContaining({
            document_id: "doc-1",
            page: 7,
            text: "Se admite anticipo del 10% contra póliza.",
            document_name: "Pliego.pdf",
          }),
        ],
        sources: [
          expect.objectContaining({
            id: 0,
            document_id: "doc-1",
            page: 7,
            text: "Se admite anticipo del 10% contra póliza.",
            document_name: "Pliego.pdf",
          }),
        ],
      }),
    );
  });

  test("objeto y alcance se mantiene como párrafo fuera de las cards", () => {
    const analysis = makeAnalysis({
      previewCriterios: makeCategoryData([]),
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

    analysis.current_version.extracted_data.preview_criterios = {
      ...analysis.current_version.extracted_data.preview_criterios,
      narrative: {
        blocks: [
          {
            type: "bullet_list",
            items: [
              {
                text: "Tiempo de entrega: 45 días",
                resumen: "45 días",
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

    expect(screen.getByTestId("preview-object-card")).toBeInTheDocument();
    expect(screen.getByTestId("preview-object-text")).toBeInTheDocument();
    expect(screen.getAllByTestId("preview-criterion-card")).toHaveLength(1);
  });

  test("objeto y alcance muestra botón de fuente con página y permite abrir evidencia", async () => {
    const user = userEvent.setup();
    const onViewSource = vi.fn();
    const analysis = makeAnalysis({ previewCriterios: makeCategoryData([]) });

    analysis.current_version.extracted_data.objeto_alcance.narrative = {
      blocks: [
        {
          type: "paragraph",
          text: "Síntesis de objeto y alcance con fuente.",
          confidence_level: "high",
          source_ids: [0],
        },
      ],
      sources: [
        {
          id: 0,
          document_id: "doc-1",
          document_name: "Pliego.pdf",
          page: 3,
          text: "Se contrata servicio de mantenimiento integral.",
        },
      ],
    };

    render(<PreviewTab analysis={analysis} onViewSource={onViewSource} />);

    expect(screen.getByTestId("preview-object-source-button")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /pág\. 3/i }));
    expect(onViewSource).toHaveBeenCalledWith(
      expect.objectContaining({
        citation: expect.objectContaining({ page: 3, document_id: "doc-1" }),
      }),
    );
  });

  test("mantiene estado vacío cuando no hay objeto ni criterios", () => {
    const analysis = makeAnalysis({
      previewCriterios: makeCategoryData([]),
    });
    analysis.current_version.extracted_data.objeto_alcance = makeCategoryData([]);

    render(<PreviewTab analysis={analysis} />);

    expect(screen.getByTestId("preview-tab-empty")).toBeInTheDocument();
  });

  test("muestra resumen No informado con estilo muted y detalle consistente", () => {
    const analysis = makeAnalysis({
      previewCriterios: makeCategoryData([]),
    });

    analysis.current_version.extracted_data.preview_criterios = {
      ...analysis.current_version.extracted_data.preview_criterios,
      narrative: {
        blocks: [
          {
            type: "bullet_list",
            items: [
              {
                text: "Tipo de cambio: No se encontró información sobre este criterio en el pliego.",
                resumen: "No informado",
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

    const card = screen.getAllByTestId("preview-criterion-card")[0];
    const summary = within(card).getByTestId("preview-criterion-summary");
    expect(summary).toHaveTextContent("—");
    expect(within(card).getByTestId("preview-criterion-unit")).toHaveTextContent("sin información");
    expect(within(card).getByTestId("preview-criterion-value").className).toContain("cedi-preview-card-value-muted");

    expect(within(card).getByTestId("preview-criterion-detail")).toHaveTextContent(
      "No se encontró información sobre este criterio en el pliego.",
    );
  });

  test("cuando resumen es undefined usa fallback neutro guion", () => {
    const analysis = makeAnalysis({
      previewCriterios: makeCategoryData([]),
    });

    analysis.current_version.extracted_data.preview_criterios = {
      ...analysis.current_version.extracted_data.preview_criterios,
      narrative: {
        blocks: [
          {
            type: "bullet_list",
            items: [
              {
                text: "Forma de pago: Pago contra entrega.",
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

    const card = screen.getAllByTestId("preview-criterion-card")[0];
    const summary = within(card).getByTestId("preview-criterion-summary");
    expect(summary).toHaveTextContent("—");
    expect(within(card).getByTestId("preview-criterion-unit")).toHaveTextContent("sin información");
    expect(within(card).getByTestId("preview-criterion-value").className).toContain("cedi-preview-card-value-muted");
  });

  test("cuando resumen tiene dato real usa estilo enfatizado", () => {
    const analysis = makeAnalysis({
      previewCriterios: makeCategoryData([]),
    });

    analysis.current_version.extracted_data.preview_criterios = {
      ...analysis.current_version.extracted_data.preview_criterios,
      narrative: {
        blocks: [
          {
            type: "bullet_list",
            items: [
              {
                text: "Mantenimiento de oferta: 60 días corridos.",
                resumen: "60 días",
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

    const card = screen.getAllByTestId("preview-criterion-card")[0];
    const summary = within(card).getByTestId("preview-criterion-summary");
    expect(within(card).getByTestId("preview-criterion-value")).toHaveTextContent("60");
    expect(within(card).getByTestId("preview-criterion-unit")).toHaveTextContent("días");
    expect(within(card).getByTestId("preview-criterion-value").className).toContain("cedi-preview-card-value");
    expect(summary).toBeInTheDocument();
  });

  test("listado de cards usa grid responsive auto-fill de 210px", () => {
    const analysis = makeAnalysis({
      previewCriterios: makeCategoryData([]),
    });

    analysis.current_version.extracted_data.preview_criterios = {
      ...analysis.current_version.extracted_data.preview_criterios,
      narrative: {
        blocks: [
          {
            type: "bullet_list",
            items: [
              {
                text: "Responsabilidad por costos logísticos o de instalación: A cargo del proveedor con condiciones adicionales extensas para validar wrapping del texto.",
                resumen: "A cargo del proveedor",
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

    expect(screen.getByTestId("preview-criteria-cards").className).toContain("grid");
    expect(screen.getByTestId("preview-criteria-cards").className).toContain("grid-cols-[repeat(auto-fill,minmax(210px,1fr))]");
    expect(screen.getByTestId("preview-criterion-card").className).toContain("min-h-[132px]");
  });

  test("consistencia resumen-detalle para 10 criterios con mix success/not_found", () => {
    const analysis = makeAnalysis({ previewCriterios: makeCategoryData([]) });

    analysis.current_version.extracted_data.preview_criterios = {
      ...analysis.current_version.extracted_data.preview_criterios,
      narrative: {
        blocks: [
          {
            type: "bullet_list",
            items: [
              { text: "Mantenimiento de oferta: Vigencia de 60 días corridos.", resumen: "60 días", confidence_level: "high", source_ids: [0] },
              { text: "Tiempo de entrega: Entrega a 45 días de la orden.", resumen: "45 días", confidence_level: "high", source_ids: [1] },
              { text: "Forma de pago: Pago a 30 días contra conformidad.", resumen: "30 días", confidence_level: "high", source_ids: [2] },
              { text: "Licitación en pesos o dólares: Cotización en pesos argentinos.", resumen: "En pesos", confidence_level: "high", source_ids: [3] },
              { text: "Tipo de cambio: No se encontró información sobre este criterio en el pliego.", resumen: "No informado", confidence_level: "low", source_ids: [] },
              { text: "Garantías o cauciones: Garantía de oferta del 1%.", resumen: "1%", confidence_level: "high", source_ids: [4] },
              { text: "Multas o penalidades: Penalidad del 0,5% por día de atraso.", resumen: "0,5% diario", confidence_level: "high", source_ids: [5] },
              { text: "Anticipo financiero requerido: No se exige anticipo financiero.", resumen: "No", confidence_level: "high", source_ids: [6] },
              { text: "Requisitos técnicos o certificaciones excluyentes: ISO 9001 obligatoria.", resumen: "ISO 9001", confidence_level: "high", source_ids: [7] },
              { text: "Responsabilidad por costos logísticos o de instalación: Costos a cargo del proveedor.", resumen: "Proveedor", confidence_level: "high", source_ids: [8] },
            ],
          },
        ],
        sources: [
          { id: 0, document_id: "doc-1", document_name: "Pliego.pdf", page: 2, text: "Mantenimiento 60 días." },
          { id: 1, document_id: "doc-1", document_name: "Pliego.pdf", page: 3, text: "Entrega 45 días." },
          { id: 2, document_id: "doc-1", document_name: "Pliego.pdf", page: 4, text: "Pago a 30 días." },
          { id: 3, document_id: "doc-1", document_name: "Pliego.pdf", page: 5, text: "Cotización en pesos." },
          { id: 4, document_id: "doc-1", document_name: "Pliego.pdf", page: 6, text: "Garantía 1%." },
          { id: 5, document_id: "doc-1", document_name: "Pliego.pdf", page: 7, text: "Penalidad 0,5%." },
          { id: 6, document_id: "doc-1", document_name: "Pliego.pdf", page: 8, text: "No anticipo." },
          { id: 7, document_id: "doc-1", document_name: "Pliego.pdf", page: 9, text: "ISO 9001." },
          { id: 8, document_id: "doc-1", document_name: "Pliego.pdf", page: 10, text: "Costos a cargo del proveedor." },
        ],
      },
    };

    render(<PreviewTab analysis={analysis} />);

    const cards = screen.getAllByTestId("preview-criterion-card");
    expect(cards).toHaveLength(10);

    for (const card of cards) {
      const unit = within(card).queryByTestId("preview-criterion-unit")?.textContent?.trim() ?? "";
      const detail = within(card).getByTestId("preview-criterion-detail").textContent ?? "";

      if (unit === "sin información") {
        expect(detail).toContain("No se encontró información");
      } else {
        expect(detail).not.toContain("No se encontró información");
      }
    }
  });

  test("multas o penalidades con varias filas muestra todos los hechos en el detalle", () => {
    const analysis = makeAnalysis({ previewCriterios: makeCategoryData([]) });

    analysis.current_version.extracted_data.preview_criterios = {
      ...analysis.current_version.extracted_data.preview_criterios,
      narrative: {
        blocks: [
          {
            type: "bullet_list",
            items: [
              {
                text:
                  "Multas o penalidades: 0,5% del abono mensual por hora.\n" +
                  "0,5% del monto total por día corrido de demora.\n" +
                  "0,25% del monto total por día hábil de demora.",
                resumen: "Varias tasas",
                confidence_level: "high",
                source_ids: [0],
              },
            ],
          },
        ],
        sources: [{ id: 0, document_id: "doc-1", document_name: "Pliego.pdf", page: 41, text: "0,5% del abono mensual por hora." }],
      },
    };

    render(<PreviewTab analysis={analysis} />);

    const card = screen.getByTestId("preview-criterion-card");
    const detail = within(card).getByTestId("preview-criterion-detail");
    expect(detail).toHaveTextContent("0,5% del abono mensual por hora.");
    expect(detail).toHaveTextContent("0,5% del monto total por día corrido de demora.");
    expect(detail).toHaveTextContent("0,25% del monto total por día hábil de demora.");
  });

  test("no pierde criterios ni fuentes respecto del bullet_list plano pre-epic-p5", () => {
    const analysis = makeAnalysis({ previewCriterios: makeCategoryData([]) });

    analysis.current_version.extracted_data.preview_criterios = {
      ...analysis.current_version.extracted_data.preview_criterios,
      narrative: {
        blocks: [
          {
            type: "bullet_list",
            items: [
              { text: "Mantenimiento de oferta: 60 días.", resumen: "60 días", confidence_level: "high", source_ids: [0] },
              { text: "Forma de pago: 30 días.", resumen: "30 días", confidence_level: "high", source_ids: [1] },
              { text: "Tipo de cambio: No se encontró información sobre este criterio en el pliego.", resumen: "No informado", confidence_level: "low", source_ids: [] },
            ],
          },
        ],
        sources: [
          { id: 0, document_id: "doc-1", document_name: "Pliego.pdf", page: 2, text: "Mantenimiento 60 días." },
          { id: 1, document_id: "doc-1", document_name: "Pliego.pdf", page: 4, text: "Pago a 30 días." },
        ],
      },
    };

    const expectedTitles = [
      "Mantenimiento de oferta",
      "Forma de pago",
      "Tipo de cambio",
    ];
    const expectedSourcePagesByTitle = new Map<string, number[]>([
      ["Mantenimiento de oferta", [2]],
      ["Forma de pago", [4]],
      ["Tipo de cambio", []],
    ]);

    render(<PreviewTab analysis={analysis} />);

    const cards = screen.getAllByTestId("preview-criterion-card");
    expect(cards).toHaveLength(expectedTitles.length);

    for (const expectedTitle of expectedTitles) {
      expect(screen.getByText(expectedTitle)).toBeInTheDocument();
    }

    for (const card of cards) {
      const title = within(card).getByTestId("preview-criterion-title").textContent?.trim() ?? "";
      const expectedPages = expectedSourcePagesByTitle.get(title) ?? [];

      if (expectedPages.length === 0) {
        expect(within(card).queryByRole("button", { name: /Ver fuente en el pliego|Ver fuentes en el pliego/i })).not.toBeInTheDocument();
      } else {
        const pageToken = expectedPages.length === 1 ? `pág. ${expectedPages[0]}` : `${expectedPages.length} fuentes`;
        expect(within(card).getAllByRole("button", { name: new RegExp(pageToken, "i") }).length).toBeGreaterThan(0);
      }
    }
  });

  test("con varias fuentes muestra la cantidad en vez de listar todas las páginas juntas", async () => {
    const user = userEvent.setup();
    const onViewSource = vi.fn();
    const analysis = makeAnalysis({ previewCriterios: makeCategoryData([]) });

    analysis.current_version.extracted_data.preview_criterios = {
      ...analysis.current_version.extracted_data.preview_criterios,
      narrative: {
        blocks: [
          {
            type: "bullet_list",
            items: [
              {
                text: "Garantías o cauciones: Integración en 15 días (art. 21) vs 10 días (anexo I).",
                resumen: "1 conflicto",
                confidence_level: "low",
                source_ids: [0, 1],
              },
            ],
          },
        ],
        sources: [
          { id: 0, document_id: "doc-1", document_name: "Pliego.pdf", page: 22, text: "Integración en 15 días." },
          { id: 1, document_id: "doc-1", document_name: "Anexo.pdf", page: 41, text: "Integración en 10 días." },
        ],
      },
    };

    render(<PreviewTab analysis={analysis} onViewSource={onViewSource} />);

    const card = screen.getByTestId("preview-criterion-card");
    const sourceButton = within(card).getByRole("button", { name: /Ver fuentes en el pliego/i });
    expect(sourceButton).toHaveTextContent("2 fuentes");
    expect(sourceButton).not.toHaveTextContent("22");
    expect(sourceButton).not.toHaveTextContent("41");

    await user.click(sourceButton);
    expect(onViewSource).toHaveBeenCalledWith(
      expect.objectContaining({
        citations: expect.arrayContaining([
          expect.objectContaining({ page: 22 }),
          expect.objectContaining({ page: 41 }),
        ]),
      }),
    );
  });

  test("muestra el panel de decisión (mismo componente que la pestaña Estado) cuando el estado de negocio está pendiente", async () => {
    const user = userEvent.setup();
    const onApproveDecision = vi.fn();
    const analysis = makeAnalysis({ previewCriterios: makeCategoryData([]) });
    analysis.business_status = "pendiente_decision";

    render(<PreviewTab analysis={analysis} onApproveDecision={onApproveDecision} />);

    expect(screen.getByTestId("business-decision-panel")).toBeInTheDocument();
    expect(screen.getByText("¿Aprobamos esta licitación para el análisis completo?")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Aprobar y analizar Fase 2/i }));
    expect(onApproveDecision).toHaveBeenCalledTimes(1);
  });

  test("permite rechazar el panel de decisión con un motivo", async () => {
    const user = userEvent.setup();
    const onRejectDecision = vi.fn();
    const analysis = makeAnalysis({ previewCriterios: makeCategoryData([]) });
    analysis.business_status = "pendiente_decision";

    render(<PreviewTab analysis={analysis} onRejectDecision={onRejectDecision} />);

    expect(screen.getByTestId("business-decision-panel")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "No aprobar" }));
    await user.type(screen.getByLabelText("Motivo (opcional)"), "Fuera de alcance");
    await user.click(screen.getByRole("button", { name: "Confirmar: no aprobar" }));
    expect(onRejectDecision).toHaveBeenCalledWith("Fuera de alcance");
  });

  test("no muestra el panel de decisión cuando el estado de negocio no está pendiente", () => {
    const analysis = makeAnalysis({ previewCriterios: makeCategoryData([]) });
    analysis.business_status = "en_revision";

    render(<PreviewTab analysis={analysis} />);

    expect(screen.queryByTestId("business-decision-panel")).not.toBeInTheDocument();
  });

  test("muestra un aviso cuando la decisión ya fue rechazada", () => {
    const analysis = makeAnalysis({ previewCriterios: makeCategoryData([]) });

    render(
      <PreviewTab
        analysis={analysis}
        categoriesDecision="rejected"
        categoriesDecisionByName="Agostina Torres"
        categoriesDecisionAt="2026-09-25T12:00:00Z"
      />,
    );

    expect(screen.getByTestId("categories-decision-rejected-banner")).toHaveTextContent(
      "Rechazado por Agostina Torres",
    );
  });
});
