import { render, screen } from "@testing-library/react";

import { FieldBadge } from "./FieldBadge";

describe("FieldBadge", () => {
  test("muestra 'Alta' con color de confianza alta", () => {
    render(<FieldBadge level="high" />);

    const badge = screen.getByText("Alta");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass("bg-[rgba(127,243,222,.35)]", "text-[#0B6B58]");
    expect(badge).toHaveAttribute("title", "Nivel de confianza: alta");
  });

  test("muestra 'Media' con color de confianza media", () => {
    render(<FieldBadge level="medium" />);

    const badge = screen.getByText("Media");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass("bg-[rgba(169,102,255,.14)]", "text-[#6E2FC9]");
  });

  test("muestra 'Baja' con color de confianza baja", () => {
    render(<FieldBadge level="low" />);

    const badge = screen.getByText("Baja");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass("bg-[#FEE2E2]", "text-[#DC2626]");
  });
});
