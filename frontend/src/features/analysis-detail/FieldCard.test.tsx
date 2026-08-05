import { render, screen } from "@testing-library/react";

import { FieldCard } from "./FieldCard";
import type { FieldItem } from "./types";

function createField(
  field_name: string,
  options?: {
    state?: FieldItem["field_state"];
    value?: string | null;
    confidence?: number;
    citations?: FieldItem["citations"];
  },
): FieldItem {
  return {
    field_name,
    field_value: options?.value ?? "valor",
    field_state: options?.state ?? "extraido",
    confidence: options?.confidence ?? 0.9,
    citations:
      options?.citations ?? [
        {
          text: "Artículo 1: cita de ejemplo para test",
          page: 2,
          document_id: "doc-1",
          document_name: "Pliego.pdf",
        },
      ],
  };
}

describe("FieldCard", () => {
  test("T1: Campo extraído con confianza alta muestra badge verde y botón Ver fuente", () => {
    const field = createField("monto_garantia", {
      state: "extraido",
      value: "5%",
      confidence: 0.9,
    });

    render(<FieldCard field={field} />);

    expect(screen.getByText("ALTA")).toHaveClass("bg-success-light", "text-success");
    expect(screen.getByRole("button", { name: /ver fuente/i })).toBeInTheDocument();
  });

  test("T2: Campo con confianza media muestra badge amarillo y botón Corregir destacado", () => {
    const field = createField("plazo", {
      state: "extraido",
      confidence: 0.65,
    });

    render(<FieldCard field={field} />);

    expect(screen.getByText("MEDIA")).toHaveClass("bg-warning-light", "text-warning");
    expect(screen.getByRole("button", { name: /corregir/i })).toHaveClass("bg-warning");
  });

  test("T3: Campo no encontrado muestra fondo amarillo y botón Agregar manualmente", () => {
    const field = createField("garantia_anticipo", {
      state: "no_encontrado",
      value: null,
      confidence: 0,
      citations: [],
    });

    render(<FieldCard field={field} />);

    expect(screen.getByTestId("field-card")).toHaveClass("bg-warning-light");
    expect(screen.getByText("No se encontró este dato")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /agregar manualmente/i })).toBeInTheDocument();
  });

  test("T4: Campo en conflicto muestra ambos valores con fuentes", () => {
    const field = createField("monto_garantia", {
      state: "en_conflicto",
      value: null,
      confidence: 0.4,
      citations: [
        {
          text: "5%",
          value: "5%",
          page: 10,
          document_id: "doc-a",
          document_name: "Pliego.pdf",
        },
        {
          text: "8%",
          value: "8%",
          page: 3,
          document_id: "doc-b",
          document_name: "Anexo.pdf",
        },
      ],
    });

    render(<FieldCard field={field} />);

    expect(screen.getByTestId("field-card")).toHaveClass("border-l-error", "bg-error-light");
    expect(screen.getByText("5%")).toBeInTheDocument();
    expect(screen.getByText("8%")).toBeInTheDocument();
    expect(screen.getAllByText("Pliego.pdf (pág. 10)").length).toBeGreaterThan(0);
    expect(screen.getByText("Anexo.pdf (pág. 3)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /resolver conflicto/i })).toBeInTheDocument();
  });

  test("T5: Campo muestra cita resumida y fuente", () => {
    const field = createField("objeto", {
      state: "extraido",
      value: "Adquisición de equipamiento informático",
      citations: [
        {
          text: "Artículo 1: El objeto de la presente licitación es la adquisición de equipamiento informático para laboratorios.",
          page: 2,
          document_id: "doc-1",
          document_name: "Pliego.pdf",
        },
      ],
    });

    render(<FieldCard field={field} />);

    expect(screen.getByText(/Artículo 1: El objeto de la presente/i)).toBeInTheDocument();
    expect(screen.getByText("Pliego.pdf (pág. 2)")).toBeInTheDocument();
  });
});
