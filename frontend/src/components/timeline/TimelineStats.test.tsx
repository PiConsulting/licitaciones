import { render, screen } from "@testing-library/react";
import { TimelineStats } from "./TimelineStats";

describe("TimelineStats", () => {
  test("muestra cards KPI con labels del mockup", () => {
    render(
      <TimelineStats
        totalEvents={10}
        confirmedEvents={7}
        pendingEvents={3}
        completedEvents={4}
        nextUpcomingEvent={{ name: "Apertura de sobres", date: "2026-09-18" }}
      />,
    );

    expect(screen.getByText("Hitos")).toBeInTheDocument();
    expect(screen.getByText("Cumplidos")).toBeInTheDocument();
    expect(screen.getByText("Próximo vencimiento")).toBeInTheDocument();
  });

  test("muestra total de hitos y cumplidos", () => {
    render(
      <TimelineStats
        totalEvents={10}
        confirmedEvents={7}
        pendingEvents={3}
        completedEvents={4}
        nextUpcomingEvent={{ name: "Apertura de sobres", date: "2026-09-18" }}
      />,
    );

    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
  });

  test("muestra evento próximo y detalle corto", () => {
    render(
      <TimelineStats
        totalEvents={10}
        confirmedEvents={7}
        pendingEvents={3}
        completedEvents={4}
        nextUpcomingEvent={{ name: "Apertura de sobres", date: "2026-09-18" }}
      />,
    );

    expect(screen.getByText(/Apertura de sobres/)).toBeInTheDocument();
    expect(screen.getByText(/18\/09/)).toBeInTheDocument();
  });

  test("muestra fallback cuando no hay próximos eventos", () => {
    render(
      <TimelineStats
        totalEvents={7}
        confirmedEvents={7}
        pendingEvents={0}
        completedEvents={7}
        nextUpcomingEvent={null}
      />,
    );

    expect(screen.getByText("Sin fecha")).toBeInTheDocument();
    expect(screen.getByText("No hay hitos futuros confirmados")).toBeInTheDocument();
  });

  test("mantiene clase base timeline-stats", () => {
    render(
      <TimelineStats
        totalEvents={5}
        confirmedEvents={5}
        pendingEvents={0}
        completedEvents={5}
        nextUpcomingEvent={null}
      />,
    );

    const container = screen.getByTestId("timeline-stats");
    expect(container).toHaveClass("timeline-stats");
  });
});
