import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { Toast } from "./Toast";

describe("Toast", () => {
  test("renderiza toast success", () => {
    render(<Toast id="1" type="success" message="Operación exitosa" onClose={() => undefined} />);

    expect(screen.getByText("Operación exitosa")).toBeInTheDocument();
    expect(screen.getByTestId("toast")).toHaveClass("bg-success-light");
  });

  test("renderiza toast error", () => {
    render(<Toast id="1" type="error" message="Error al procesar" onClose={() => undefined} />);

    expect(screen.getByText("Error al procesar")).toBeInTheDocument();
    expect(screen.getByTestId("toast")).toHaveClass("bg-error-light");
  });

  test("permite cerrar el toast", () => {
    const onClose = vi.fn();

    render(<Toast id="toast-id" type="success" message="Test" onClose={onClose} />);

    fireEvent.click(screen.getByLabelText("Cerrar notificación"));
    expect(onClose).toHaveBeenCalledWith("toast-id");
  });
});
