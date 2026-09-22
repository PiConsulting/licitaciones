import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TimelineVerticalView } from "./TimelineVerticalView";
import { ConfirmedEvent } from "./EventCard";

const createMockEvent = (overrides?: Partial<ConfirmedEvent>): ConfirmedEvent => ({
  id: "evt-1",
  event_id: "evt-1",
  analysis_id: "analysis-456",
  name: "Evento",
  event_date: "2026-09-10",
  date_source: "detected",
  status: "confirmed",
  deleted: false,
  hidden: false,
  created_at: "2026-08-28T12:00:00Z",
  updated_at: "2026-08-28T12:00:00Z",
  ...overrides,
});

const noop = () => [];

describe("TimelineVerticalView", () => {
  beforeEach(() => {
    // Fecha fija para que la posición de "HOY" en la línea sea determinística.
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 8, 1)); // 2026-09-01
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  test("no renderiza nada si no hay eventos con fecha", () => {
    const { container } = render(
      <TimelineVerticalView
        events={[]}
        getDependentDeadlines={noop}
        getDependentEventNames={noop}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  test("renderiza un punto por evento y el marcador HOY entre pasados y futuros", () => {
    const events = [
      createMockEvent({ event_id: "evt-past", name: "Apertura de ofertas", event_date: "2026-08-20" }),
      createMockEvent({ event_id: "evt-future", name: "Adjudicación", event_date: "2026-09-10" }),
    ];

    render(
      <TimelineVerticalView
        events={events}
        getDependentDeadlines={noop}
        getDependentEventNames={noop}
      />,
    );

    expect(screen.getByText("Apertura de ofertas")).toBeInTheDocument();
    expect(screen.getByText("Adjudicación")).toBeInTheDocument();
    expect(screen.getByText(/^HOY/)).toBeInTheDocument();

    const items = screen.getAllByRole("listitem");
    const labels = items.map((li) => li.textContent);
    const pastIdx = labels.findIndex((t) => t?.includes("Apertura de ofertas"));
    const todayIdx = labels.findIndex((t) => t?.includes("HOY"));
    const futureIdx = labels.findIndex((t) => t?.includes("Adjudicación"));

    expect(pastIdx).toBeLessThan(todayIdx);
    expect(todayIdx).toBeLessThan(futureIdx);
  });

  test("muestra HOY al final si todos los eventos ya pasaron", () => {
    const events = [
      createMockEvent({ event_id: "evt-1", name: "Recepción de pliego", event_date: "2026-01-10" }),
      createMockEvent({ event_id: "evt-2", name: "Apertura de ofertas", event_date: "2026-02-10" }),
    ];

    render(
      <TimelineVerticalView
        events={events}
        getDependentDeadlines={noop}
        getDependentEventNames={noop}
      />,
    );

    const items = screen.getAllByRole("listitem");
    const labels = items.map((li) => li.textContent);
    expect(labels[labels.length - 1]).toContain("HOY");
  });

  test("abre el detalle del evento al hacer click", async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    const events = [createMockEvent({ name: "Firma de contrato" })];

    render(
      <TimelineVerticalView
        events={events}
        getDependentDeadlines={noop}
        getDependentEventNames={noop}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Firma de contrato/ }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getAllByText("Firma de contrato").length).toBeGreaterThan(1);
  });

  test("muestra 'Usado por' cuando hay eventos dependientes", () => {
    const events = [createMockEvent({ name: "Adjudicación" })];

    render(
      <TimelineVerticalView
        events={events}
        getDependentDeadlines={noop}
        getDependentEventNames={() => ["Entrega de equipamiento"]}
      />,
    );

    expect(screen.getByText(/Usado por: Entrega de equipamiento/)).toBeInTheDocument();
  });

  test("muestra badge 'Oculto' y atenúa el evento oculto", () => {
    const events = [createMockEvent({ name: "Notificación de fuerza mayor", hidden: true })];

    render(
      <TimelineVerticalView
        events={events}
        getDependentDeadlines={noop}
        getDependentEventNames={noop}
      />,
    );

    expect(screen.getByText("Oculto")).toBeInTheDocument();
  });
});
