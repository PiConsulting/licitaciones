import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TimelineEmptyState } from "./TimelineEmptyState";

describe("TimelineEmptyState", () => {
  test("renders empty state with icon and text", () => {
    const handleAddEvent = vi.fn();

    render(<TimelineEmptyState onAddEvent={handleAddEvent} />);

    expect(screen.getByText("No se encontraron eventos temporales")).toBeInTheDocument();
    expect(
      screen.getByText(/El análisis IA no detectó eventos o plazos temporales/)
    ).toBeInTheDocument();
  });

  test("renders add event button", () => {
    const handleAddEvent = vi.fn();

    render(<TimelineEmptyState onAddEvent={handleAddEvent} />);

    const button = screen.getByRole("button", { name: /Agregar evento/i });
    expect(button).toBeInTheDocument();
  });

  test("calls onAddEvent when button is clicked", async () => {
    const user = userEvent.setup();
    const handleAddEvent = vi.fn();

    render(<TimelineEmptyState onAddEvent={handleAddEvent} />);

    const button = screen.getByRole("button", { name: /Agregar evento/i });
    await user.click(button);

    expect(handleAddEvent).toHaveBeenCalledTimes(1);
  });

  test("has correct styling and structure", () => {
    const handleAddEvent = vi.fn();

    render(<TimelineEmptyState onAddEvent={handleAddEvent} />);

    const container = screen.getByText("No se encontraron eventos temporales").closest(".timeline-empty-state");
    expect(container).toHaveClass("flex", "flex-col", "items-center", "justify-center");
  });

  test("displays descriptive text about manual event creation", () => {
    const handleAddEvent = vi.fn();

    render(<TimelineEmptyState onAddEvent={handleAddEvent} />);

    expect(
      screen.getByText(/Podés agregar eventos manualmente para construir la línea de tiempo/)
    ).toBeInTheDocument();
  });
});
