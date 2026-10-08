import { render, screen } from "@testing-library/react";
import { ErrorIndicator } from "./ErrorIndicator";

describe("ErrorIndicator", () => {
  test("renders error message", () => {
    const error = "Tipo de día no especificado en documento fuente";

    render(<ErrorIndicator error={error} />);

    expect(screen.getByText("No se pudo calcular:")).toBeInTheDocument();
    expect(screen.getByText(/Tipo de día no especificado/)).toBeInTheDocument();
  });

  test("displays full error text", () => {
    const error = "Ciclo de dependencia detectado entre eventos";

    render(<ErrorIndicator error={error} />);

    expect(screen.getByText(/Ciclo de dependencia detectado/)).toBeInTheDocument();
  });

  test("has correct error styling", () => {
    const error = "Error de cálculo";

    render(<ErrorIndicator error={error} />);

    const container = screen.getByText("No se pudo calcular:").closest(".error-indicator");
    expect(container).toHaveClass("bg-red-50", "border-red-200");
  });

  test("shows alert icon", () => {
    const error = "Error de cálculo";

    const { container } = render(<ErrorIndicator error={error} />);

    // lucide-react icons render as svg
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
  });
});
