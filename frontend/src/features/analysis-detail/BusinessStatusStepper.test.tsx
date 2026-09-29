import { render, screen, within } from "@testing-library/react";

import { BusinessStatusStepper } from "./components/BusinessStatusStepper";

describe("BusinessStatusStepper", () => {
  it("marca el paso actual y deja pendiente la decisión", () => {
    render(<BusinessStatusStepper status="pendiente_decision" />);

    const items = within(screen.getByTestId("business-status-stepper")).getAllByRole("listitem");
    expect(items).toHaveLength(5);
    expect(items[1]).toHaveAttribute("aria-current", "step");
    expect(within(items[1]).getByText("Pendiente")).toBeInTheDocument();
  });

  it("muestra la licitación no aprobada como paso terminal", () => {
    render(<BusinessStatusStepper status="no_aprobada" />);

    const items = within(screen.getByTestId("business-status-stepper")).getAllByRole("listitem");
    expect(within(items[1]).getByText("No aprobada")).toBeInTheDocument();
    expect(within(items[1]).getByText("No sigue")).toBeInTheDocument();
    expect(items.some((item) => item.getAttribute("aria-current") === "step")).toBe(false);
  });

  it("muestra fecha de presentación y resultado final", () => {
    render(<BusinessStatusStepper status="ganada" presentedAt="2026-09-18" />);

    const items = within(screen.getByTestId("business-status-stepper")).getAllByRole("listitem");
    expect(within(items[3]).getByText("18/09/2026")).toBeInTheDocument();
    expect(within(items[4]).getByText("Ganada")).toBeInTheDocument();
  });
});
