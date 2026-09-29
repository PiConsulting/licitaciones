import { render, screen } from "@testing-library/react";

import { ConfidenceBadge } from "./ConfidenceBadge";

describe("ConfidenceBadge", () => {
  test("renderiza 'Alta' para confianza >= 0.8 con estilo success de maqueta", () => {
    render(<ConfidenceBadge confidence={0.8} />);

    const badge = screen.getByText("Alta");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass("bg-[rgba(127,243,222,.35)]", "text-[#0B6B58]");
  });

  test("renderiza 'Media' para confianza >= 0.6 y < 0.8", () => {
    render(<ConfidenceBadge confidence={0.6} />);

    const badge = screen.getByText("Media");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass("bg-[rgba(169,102,255,.14)]", "text-[#6E2FC9]");
  });

  test("renderiza 'Baja' para confianza < 0.6", () => {
    render(<ConfidenceBadge confidence={0.59} />);

    const badge = screen.getByText("Baja");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass("bg-[#FEE2E2]", "text-[#DC2626]");
  });

  test("renderiza fallback neutral cuando no hay confianza", () => {
    render(<ConfidenceBadge confidence={null} />);

    const badge = screen.getByText("Sin dato");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass("bg-cedi-navy-8", "text-cedi-navy-68");
  });
});
