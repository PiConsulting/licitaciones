import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, test, expect, vi } from "vitest";
import { DeadlineDetailModal } from "./DeadlineDetailModal";
import type { DeadlineResponse, EventResponse } from "../../types/timeline";

describe("DeadlineDetailModal", () => {
  const mockTriggerEvent: EventResponse = {
    id: "event-1",
    event_id: "evt-trigger",
    analysis_id: "analysis-1",
    name: "Adjudicación",
    event_date: "2026-09-10",
    date_source: "detected",
    status: "confirmed",
    deleted: false,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  };

  const mockTargetEvent: EventResponse = {
    id: "event-2",
    event_id: "evt-target",
    analysis_id: "analysis-1",
    name: "Entrega de equipamiento",
    event_date: "2026-10-25",
    date_source: "calculated",
    status: "confirmed",
    deleted: false,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  };

  const mockDeadline: DeadlineResponse = {
    id: "deadline-1",
    deadline_id: "dl-1",
    analysis_id: "analysis-1",
    name: "Entrega de equipamiento",
    trigger_event_id: "evt-trigger",
    target_event_id: "evt-target",
    duration: 45,
    unit: "días",
    day_type: "corridos",
    es_plazo_maximo: true,
    deadline_date: "2026-10-25",
    calculation_status: "calculated",
    deleted: false,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  };

  test("shows deadline details with trigger and target events", () => {
    render(
      <DeadlineDetailModal
        deadline={mockDeadline}
        triggerEvent={mockTriggerEvent}
        targetEvent={mockTargetEvent}
        open={true}
        onClose={() => {}}
      />
    );

    expect(screen.getByText("Detalle del plazo")).toBeInTheDocument();
    expect(screen.getByText("Adjudicación")).toBeInTheDocument();
    expect(screen.getByText("Entrega de equipamiento")).toBeInTheDocument();
    expect(screen.getByText(/45 días/i)).toBeInTheDocument();
    expect(screen.getByText(/corridos/i)).toBeInTheDocument();
  });

  test("shows trigger event date", () => {
    render(
      <DeadlineDetailModal
        deadline={mockDeadline}
        triggerEvent={mockTriggerEvent}
        targetEvent={mockTargetEvent}
        open={true}
        onClose={() => {}}
      />
    );

    expect(screen.getByText("10/09/2026")).toBeInTheDocument();
  });

  test("shows calculated deadline date", () => {
    render(
      <DeadlineDetailModal
        deadline={mockDeadline}
        triggerEvent={mockTriggerEvent}
        targetEvent={mockTargetEvent}
        open={true}
        onClose={() => {}}
      />
    );

    expect(screen.getByText("25/10/2026")).toBeInTheDocument();
  });

  test("shows calculation status badge", () => {
    render(
      <DeadlineDetailModal
        deadline={mockDeadline}
        triggerEvent={mockTriggerEvent}
        targetEvent={mockTargetEvent}
        open={true}
        onClose={() => {}}
      />
    );

    expect(screen.getByText("Calculada")).toBeInTheDocument();
  });

  test("shows error when calculation failed", () => {
    const errorDeadline: DeadlineResponse = {
      ...mockDeadline,
      calculation_status: "error",
      calculation_error: "Tipo de día no especificado en el documento",
      deadline_date: null,
    };

    render(
      <DeadlineDetailModal
        deadline={errorDeadline}
        triggerEvent={mockTriggerEvent}
        targetEvent={mockTargetEvent}
        open={true}
        onClose={() => {}}
      />
    );

    expect(screen.getByText("Error")).toBeInTheDocument();
    expect(screen.getByText(/No se pudo calcular/i)).toBeInTheDocument();
    // El texto del error aparece dos veces (badge + bloque de error), así que verificamos que existe al menos una vez
    expect(screen.getAllByText(/Tipo de día no especificado/i).length).toBeGreaterThan(0);
  });

  test("shows pending when deadline date is not calculated", () => {
    const pendingDeadline: DeadlineResponse = {
      ...mockDeadline,
      calculation_status: "pending",
      deadline_date: null,
    };

    render(
      <DeadlineDetailModal
        deadline={pendingDeadline}
        triggerEvent={mockTriggerEvent}
        targetEvent={mockTargetEvent}
        open={true}
        onClose={() => {}}
      />
    );

    // "Pendiente" aparece en el badge y en la fecha, verificamos que existe
    const pendingElements = screen.getAllByText("Pendiente");
    expect(pendingElements.length).toBeGreaterThan(0);
  });

  test("shows source information when deadline has source", () => {
    const deadlineWithSource: DeadlineResponse = {
      ...mockDeadline,
      source_document_id: "doc-123",
      source_page: 5,
      source_fragment: "Plazo de 45 días corridos desde la adjudicación",
    };

    render(
      <DeadlineDetailModal
        deadline={deadlineWithSource}
        triggerEvent={mockTriggerEvent}
        targetEvent={mockTargetEvent}
        open={true}
        onClose={() => {}}
      />
    );

    expect(screen.getByText(/fuente en el documento/i)).toBeInTheDocument();
    expect(screen.getByText(/página 5/i)).toBeInTheDocument();
    expect(screen.getByText(/plazo de 45 días corridos/i)).toBeInTheDocument();
  });

  test("calls onViewSource when source button is clicked", async () => {
    const user = userEvent.setup();
    const onViewSource = vi.fn();
    const deadlineWithSource: DeadlineResponse = {
      ...mockDeadline,
      source_document_id: "doc-123",
      source_page: 5,
    };

    render(
      <DeadlineDetailModal
        deadline={deadlineWithSource}
        triggerEvent={mockTriggerEvent}
        targetEvent={mockTargetEvent}
        open={true}
        onClose={() => {}}
        onViewSource={onViewSource}
      />
    );

    const viewButton = screen.getByLabelText(/ver fuente en el pliego/i);
    await user.click(viewButton);

    expect(onViewSource).toHaveBeenCalledWith("doc-123", 5);
  });

  test("shows pending date for trigger event when date is null", () => {
    const pendingTrigger: EventResponse = {
      ...mockTriggerEvent,
      event_date: null,
      date_source: "pending",
    };

    render(
      <DeadlineDetailModal
        deadline={mockDeadline}
        triggerEvent={pendingTrigger}
        targetEvent={mockTargetEvent}
        open={true}
        onClose={() => {}}
      />
    );

    expect(screen.getByText("Fecha pendiente")).toBeInTheDocument();
  });

  test("does not render when open is false", () => {
    render(
      <DeadlineDetailModal
        deadline={mockDeadline}
        triggerEvent={mockTriggerEvent}
        targetEvent={mockTargetEvent}
        open={false}
        onClose={() => {}}
      />
    );

    expect(screen.queryByText("Detalle del plazo")).not.toBeInTheDocument();
  });

  test("shows close button", () => {
    render(
      <DeadlineDetailModal
        deadline={mockDeadline}
        triggerEvent={mockTriggerEvent}
        targetEvent={mockTargetEvent}
        open={true}
        onClose={() => {}}
      />
    );

    expect(screen.getByRole("button", { name: /cerrar/i })).toBeInTheDocument();
  });
});
