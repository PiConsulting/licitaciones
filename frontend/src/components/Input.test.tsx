import { render, screen } from "@testing-library/react";

import { Input } from "./Input";

describe("Input", () => {
  test("renderiza con label", () => {
    render(<Input label="Email" />);
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
  });

  test("muestra error", () => {
    render(<Input label="Email" error="Email inválido" />);
    expect(screen.getByText("Email inválido")).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveAttribute("aria-invalid", "true");
  });

  test("estado disabled", () => {
    render(<Input label="Email" disabled />);
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("textbox")).toHaveClass("bg-gray-50");
  });
});
