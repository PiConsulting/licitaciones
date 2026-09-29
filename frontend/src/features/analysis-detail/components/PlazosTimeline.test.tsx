import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PlazosTimeline } from "./PlazosTimeline";
import type { FieldItem } from "../types";

function datedField(field_name: string, fecha: string, options?: { hora?: string }): FieldItem {
  return {
    field_name,
    field_value: `${fecha} ${options?.hora ?? ""}`.trim(),
    field_state: "extraido",
    confidence: 0.9,
    citations: [{ text: "Cita de prueba con longitud suficiente", page: 2, document_id: "doc-1", document_name: "Pliego.pdf" }],
    raw: { fecha, hora: options?.hora ?? null, expresion_relativa: null, texto_original: null, lugar: null },
  };
}

function undatedField(field_name: string, expresion_relativa: string): FieldItem {
  return {
    field_name,
    field_value: null,
    field_state: "extraido",
    confidence: 0.8,
    citations: [],
    raw: { fecha: null, hora: null, expresion_relativa, texto_original: null, lugar: null },
  };
}

describe("PlazosTimeline", () => {
  test("sin plazos, muestra el estado vacío", () => {
    render(<PlazosTimeline items={[]} />);
    expect(screen.getByTestId("plazos-timeline-empty")).toBeInTheDocument();
  });

  test("los plazos sin fecha se muestran como filas separadas, no apretujados en un párrafo único", () => {
    const items = [
      undatedField("Mantenimiento de oferta", "30 días corridos desde la apertura"),
      undatedField("Consultas", "Hasta 5 días antes de la apertura"),
    ];

    render(<PlazosTimeline items={items} />);

    const container = screen.getByTestId("plazos-sin-fecha");
    // Una fila por ítem, nunca un párrafo con todo encadenado (era ilegible con muchos plazos).
    expect(container.querySelectorAll('[data-testid="plazos-sin-fecha-item"]')).toHaveLength(2);
    // Título corto arriba (sin ":") y detalle en su propio párrafo debajo -- mismo patrón que el checklist, no un solo texto con "Label: valor" encadenado.
    expect(screen.getByText("Mantenimiento de oferta").tagName).toBe("SPAN");
    expect(screen.getByText("Consultas").tagName).toBe("SPAN");
    // El detalle está partido en nodos porque el número de días queda en negrita (ver test dedicado más abajo) -- se compara por fila, no por texto exacto.
    const filas = screen.getAllByTestId("plazos-sin-fecha-item");
    expect(filas[0].querySelector("p")).toHaveTextContent("30 días corridos desde la apertura");
    expect(filas[1].querySelector("p")).toHaveTextContent("Hasta 5 días antes de la apertura");
  });

  test("plazos duplicados del mismo hecho no deberían llegar dos veces (regresión de datos, no de UI)", () => {
    // La deduplicación real vive en el backend (merge_node); la UI no hace la suya, para que un bug de datos se vea en vez de esconderse.
    const items = [
      undatedField("Mantenimiento de oferta", "30 días corridos desde la apertura"),
      undatedField("Mantenimiento de oferta", "30 días corridos desde la apertura"),
    ];

    render(<PlazosTimeline items={items} />);

    const container = screen.getByTestId("plazos-sin-fecha");
    expect(container.querySelectorAll('[data-testid="plazos-sin-fecha-item"]')).toHaveLength(2);
  });

  test("con narrativa sintetizada disponible, usa el título corto del bullet en vez del field_name genérico", () => {
    // Bug real (auditoría UI 2026-09-28): esta vista ignoraba `category.narrative` (que sí
    // tiene título corto + detalle, igual que riesgos/requisitos/anexos) y mostraba
    // "field_name: texto_original completo" -- una oración larga sin separar título de detalle.
    const citation = { text: "Mantenimiento de oferta: 30 días corridos desde la apertura", page: 3, document_id: "doc-1", document_name: "Pliego.pdf" };
    const item: FieldItem = {
      field_name: "Plazo",
      field_value: null,
      field_state: "extraido",
      confidence: 0.8,
      citations: [citation],
      raw: { fecha: null, hora: null, expresion_relativa: "30 días corridos desde la apertura", texto_original: null, lugar: null },
    };

    render(
      <PlazosTimeline
        items={[item]}
        narrativeSources={[{ id: 0, document_id: "doc-1", document_name: "Pliego.pdf", page: 3, text: citation.text }]}
        narrativeBullets={[
          {
            titulo: "Mantenimiento de oferta",
            text: "La oferta debe mantenerse vigente por 30 días corridos desde la apertura.",
            confidence_level: "high",
            source_ids: [0],
          },
        ]}
      />,
    );

    expect(screen.getByText("Mantenimiento de oferta").tagName).toBe("SPAN");
    // El número queda resaltado en negrita, así que el texto del detalle está partido en varios nodos.
    expect(screen.getByText(/La oferta debe mantenerse vigente por/)).toHaveTextContent(
      "La oferta debe mantenerse vigente por 30 días corridos desde la apertura.",
    );
    // "Plazo" (el field_name genérico) no debe quedar como título visible.
    expect(screen.queryByText("Plazo")).not.toBeInTheDocument();
  });

  test("los números de plazo dentro del detalle se resaltan en negrita", () => {
    // Pedido explícito: "6 (seis) meses..." y "15 días desde la recepción
    // total del hardware" -- el número tiene que saltar a la vista sin
    // agregar una línea aparte.
    const citation = { text: "6 (seis) meses desde el inicio de la tercera etapa", page: 9, document_id: "doc-1", document_name: "Pliego.pdf" };
    const item: FieldItem = {
      field_name: "Plazo",
      field_value: null,
      field_state: "extraido",
      confidence: 0.8,
      citations: [citation],
      raw: { fecha: null, hora: null, expresion_relativa: "6 (seis) meses", texto_original: null, lugar: null },
    };

    render(
      <PlazosTimeline
        items={[item]}
        narrativeSources={[{ id: 0, document_id: "doc-1", document_name: "Pliego.pdf", page: 9, text: citation.text }]}
        narrativeBullets={[
          {
            titulo: "Garantía técnica",
            text: "6 (seis) meses, tomando como fecha inicial el inicio de la tercera etapa de migraciones con soporte.",
            confidence_level: "high",
            source_ids: [0],
          },
        ]}
      />,
    );

    const detalle = screen.getByText(/tomando como fecha inicial/);
    const negrita = within(detalle).getByText("6 (seis) meses");
    expect(negrita.tagName).toBe("STRONG");
  });

  test("números sin unidad de tiempo (ej. un artículo) no se resaltan", () => {
    const item = undatedField("Consultas", "Según el artículo 15 del pliego particular");

    render(<PlazosTimeline items={[item]} />);

    const detalle = screen.getByText(/Según el artículo/);
    expect(within(detalle).queryByText("15", { selector: "strong" })).not.toBeInTheDocument();
  });

  test("con plazos con fecha, muestra el botón de pantalla completa y abre/cierra el modal", async () => {
    const user = userEvent.setup();
    const items = [datedField("Apertura", "2026-09-15", { hora: "11:00" })];

    render(<PlazosTimeline items={items} />);

    expect(screen.queryByTestId("plazos-timeline-modal")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("plazos-timeline-fullscreen-open"));
    expect(screen.getByTestId("plazos-timeline-modal")).toBeInTheDocument();
    expect(screen.getAllByTestId("plazos-timeline-marker").length).toBeGreaterThan(0);

    await user.click(screen.getByTestId("plazos-timeline-fullscreen-close"));
    expect(screen.queryByTestId("plazos-timeline-modal")).not.toBeInTheDocument();
  });

  test("sin plazos con fecha, no muestra el botón de pantalla completa", () => {
    render(<PlazosTimeline items={[undatedField("Consultas", "Hasta 5 días antes de la apertura")]} />);
    expect(screen.queryByTestId("plazos-timeline-fullscreen-open")).not.toBeInTheDocument();
  });
});
