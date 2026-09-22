import { render, screen } from "@testing-library/react";
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
    expect(container).toHaveTextContent("Mantenimiento de oferta: 30 días corridos desde la apertura");
    expect(container).toHaveTextContent("Consultas: Hasta 5 días antes de la apertura");
    expect(screen.getByText("Mantenimiento de oferta:").tagName).toBe("STRONG");
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
