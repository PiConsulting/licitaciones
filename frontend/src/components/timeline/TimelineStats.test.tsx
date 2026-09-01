import { render, screen } from "@testing-library/react";
import { TimelineStats } from "./TimelineStats";

describe("TimelineStats", () => {
  test("renders stats with correct counts", () => {
    render(<TimelineStats totalEvents={10} confirmedEvents={7} pendingEvents={3} />);

    expect(screen.getByText("Estado de Timeline")).toBeInTheDocument();
    expect(screen.getByText(/7 de 10 eventos con fecha confirmada/)).toBeInTheDocument();
  });

  test("calculates percentage correctly", () => {
    render(<TimelineStats totalEvents={10} confirmedEvents={7} pendingEvents={3} />);

    expect(screen.getByText(/70%/)).toBeInTheDocument();
  });

  test("shows pending events count", () => {
    render(<TimelineStats totalEvents={10} confirmedEvents={7} pendingEvents={3} />);

    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("pendientes")).toBeInTheDocument();
  });

  test("does not show pending count when zero", () => {
    render(<TimelineStats totalEvents={7} confirmedEvents={7} pendingEvents={0} />);

    expect(screen.queryByText("pendientes")).not.toBeInTheDocument();
  });

  test("handles 100% completion", () => {
    render(<TimelineStats totalEvents={5} confirmedEvents={5} pendingEvents={0} />);

    expect(screen.getByText(/5 de 5 eventos con fecha confirmada/)).toBeInTheDocument();
    expect(screen.getByText(/100%/)).toBeInTheDocument();
  });

  test("handles 0% completion", () => {
    render(<TimelineStats totalEvents={5} confirmedEvents={0} pendingEvents={5} />);

    expect(screen.getByText(/0 de 5 eventos con fecha confirmada/)).toBeInTheDocument();
    expect(screen.getByText(/0%/)).toBeInTheDocument();
  });

  test("has correct styling", () => {
    render(<TimelineStats totalEvents={10} confirmedEvents={7} pendingEvents={3} />);

    const container = screen.getByText("Estado de Timeline").closest(".timeline-stats");
    expect(container).toHaveClass("bg-blue-50", "border-blue-200");
  });
});
