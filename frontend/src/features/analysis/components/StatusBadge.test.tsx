import { render, screen } from "@testing-library/react";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  test("muestra En revisión para estado en_revision", () => {
    render(<StatusBadge status="en_revision" />);

    const badge = screen.getByText("En revisión");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass("bg-amber-100", "text-amber-800");
  });
});
