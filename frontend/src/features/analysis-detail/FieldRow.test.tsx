import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { FieldRow } from "./FieldRow";
import type { FieldItem } from "./types";

function createField(overrides?: Partial<FieldItem>): FieldItem {
  return {
    field_name: "objeto",
    field_value: "Adquisición de equipamiento",
    field_state: "extraido",
    confidence: 0.92,
    citations: [{ text: "cita", page: 1, document_id: "doc-1", document_name: "Pliego.pdf" }],
    ...overrides,
  };
}

describe("FieldRow", () => {
  test("muestra nombre, valor y badge de confianza alta", () => {
    render(<FieldRow field={createField()} />);

    expect(screen.getByText("objeto")).toBeInTheDocument();
    expect(screen.getByText("Adquisición de equipamiento")).toBeInTheDocument();
    expect(screen.getByText("ALTA")).toBeInTheDocument();
  });

  test("campo no_aplica muestra badge NO APLICA", () => {
    render(<FieldRow field={createField({ field_state: "no_aplica", field_value: null })} />);
    expect(screen.getByText("NO APLICA")).toBeInTheDocument();
  });

  test("click en Ver fuente dispara onViewSource con la cita principal", async () => {
    const user = userEvent.setup();
    const onViewSource = vi.fn();
    const field = createField();

    render(<FieldRow field={field} onViewSource={onViewSource} />);
    await user.click(screen.getByRole("button", { name: /ver fuente/i }));

    expect(onViewSource).toHaveBeenCalledWith({ citation: field.citations[0], citations: field.citations });
  });

  test("click en la fila expande y muestra el valor completo sin recortar", async () => {
    const user = userEvent.setup();
    const longValue = "Un valor bastante largo que en la fila compacta quedaría recortado por el truncate";
    render(<FieldRow field={createField({ field_value: longValue })} />);

    const toggle = screen.getByRole("button", { name: /objeto/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getAllByText(longValue)).toHaveLength(1);

    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByText(longValue)).toHaveLength(2);

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getAllByText(longValue)).toHaveLength(1);
  });
});
