import { fireEvent, render, screen } from "@testing-library/react";

import { BUSINESS_UNITS } from "../../../config/businessUnits";
import type { ExpiringAlertItem } from "../hooks/useExpiringAlerts";
import { ExpiringAlertsSection } from "./ExpiringAlertsSection";

function buildAlert(overrides: Partial<ExpiringAlertItem>): ExpiringAlertItem {
  return {
    id: "a1",
    analysisId: "analysis-1",
    analysisName: "Licitación urgente",
    organismo: "Organismo A",
    businessStatus: "en_revision",
    businessUnit: BUSINESS_UNITS[0],
    eventName: "Presentación de ofertas",
    daysUntil: 2,
    dateLabel: "23/09/2026",
    additionalEvents: 0,
    ...overrides,
  };
}

function mockTrackLayout(track: HTMLElement, layout: { scrollWidth: number; clientWidth: number; scrollLeft?: number }) {
  Object.defineProperty(track, "scrollWidth", { configurable: true, value: layout.scrollWidth });
  Object.defineProperty(track, "clientWidth", { configurable: true, value: layout.clientWidth });
  Object.defineProperty(track, "scrollLeft", { configurable: true, writable: true, value: layout.scrollLeft ?? 0 });
}

describe("ExpiringAlertsSection", () => {
  test("muestra nombre del análisis, organismo, evento con fecha y badges de estado y unidad", () => {
    render(<ExpiringAlertsSection alerts={[buildAlert({ additionalEvents: 2 })]} />);

    const card = screen.getByTestId("expiring-alert-a1");
    expect(card).toHaveTextContent("Licitación urgente");
    expect(card).toHaveTextContent("Organismo A");
    expect(card).toHaveTextContent("Presentación de ofertas");
    expect(card).toHaveTextContent("23/09/2026");
    expect(card).toHaveTextContent("+2 más");
    expect(card).toHaveTextContent("En revisión");
    expect(card).toHaveTextContent(BUSINESS_UNITS[0]);
    expect(screen.getByRole("heading", { name: /1 licitación con eventos próximos/i })).toBeInTheDocument();
  });

  test("usa rojo para los eventos más cercanos y naranja para los más lejanos", () => {
    render(
      <ExpiringAlertsSection
        alerts={[buildAlert({}), buildAlert({ id: "a2", daysUntil: 10 })]}
      />,
    );

    expect(screen.getByTestId("expiring-days-a1")).toHaveStyle({ background: "#E5484D" });
    expect(screen.getByTestId("expiring-days-a2")).toHaveStyle({ background: "#F0731A" });
  });

  test("muestra Hoy cuando el evento es hoy", () => {
    render(<ExpiringAlertsSection alerts={[buildAlert({ daysUntil: 0 })]} />);

    expect(screen.getByTestId("expiring-days-a1")).toHaveTextContent("Hoy");
  });

  test("abre la alerta al hacer click", () => {
    const onOpenAlert = vi.fn();
    const alert = buildAlert({});
    render(<ExpiringAlertsSection alerts={[alert]} onOpenAlert={onOpenAlert} />);

    fireEvent.click(screen.getByTestId("expiring-alert-a1"));

    expect(onOpenAlert).toHaveBeenCalledWith(alert);
  });

  test("no muestra flechas cuando las alertas entran en una fila", () => {
    render(<ExpiringAlertsSection alerts={[buildAlert({})]} />);

    expect(screen.queryByRole("button", { name: "Más alertas" })).not.toBeInTheDocument();
  });

  test("muestra flechas de desplazamiento cuando las alertas no entran en la fila", () => {
    const { rerender } = render(<ExpiringAlertsSection alerts={[buildAlert({})]} />);
    const track = screen.getByTestId("expiring-alerts-track");
    const scrollBy = vi.fn();
    Object.defineProperty(track, "scrollBy", { configurable: true, value: scrollBy });
    mockTrackLayout(track, { scrollWidth: 1200, clientWidth: 600 });

    rerender(<ExpiringAlertsSection alerts={[buildAlert({}), buildAlert({ id: "a2" })]} />);

    const next = screen.getByRole("button", { name: "Más alertas" });
    const prev = screen.getByRole("button", { name: "Alertas anteriores" });
    expect(next).toBeEnabled();
    expect(prev).toBeDisabled();

    fireEvent.click(next);
    expect(scrollBy).toHaveBeenCalledWith(expect.objectContaining({ left: expect.any(Number), behavior: "smooth" }));

    (track as HTMLElement).scrollLeft = 600;
    fireEvent.scroll(track);

    expect(screen.getByRole("button", { name: "Más alertas" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Alertas anteriores" })).toBeEnabled();
  });

  test("no renderiza nada sin alertas", () => {
    const { container } = render(<ExpiringAlertsSection alerts={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});
