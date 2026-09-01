import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, test, expect, vi } from "vitest";
import { EventDetailModal } from "./EventDetailModal";
import type { EventResponse, DeadlineResponse } from "../../types/timeline";

describe("EventDetailModal", () => {
  const mockEvent: EventResponse = {
    id: "event-1",
    event_id: "evt-123",
    analysis_id: "analysis-1",
    name: "Adjudicación",
    event_date: "2026-09-10",
    date_source: "detected",
    status: "confirmed",
    deleted: false,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  };

  test("shows event details with date and source badge", () => {
    render(<EventDetailModal event={mockEvent} open={true} onClose={() => {}} />);

    expect(screen.getByText("Adjudicación")).toBeInTheDocument();
    expect(screen.getByText("10/09/2026")).toBeInTheDocument();
    expect(screen.getByText("Detectada")).toBeInTheDocument();
  });

  test("shows dependent deadlines when provided", () => {
    const deadlines: DeadlineResponse[] = [
      {
        id: "deadline-1",
        deadline_id: "dl-1",
        analysis_id: "analysis-1",
        name: "Entrega de equipamiento",
        duration: 45,
        unit: "días",
        day_type: "corridos",
        es_plazo_maximo: true,
        deadline_date: null,
        calculation_status: "pending",
        deleted: false,
        created_at: "2026-08-01T00:00:00Z",
        updated_at: "2026-08-01T00:00:00Z",
      },
    ];

    render(<EventDetailModal event={mockEvent} deadlines={deadlines} open={true} onClose={() => {}} />);

    expect(screen.getByText(/plazos que dependen de este evento/i)).toBeInTheDocument();
    expect(screen.getByText("Entrega de equipamiento")).toBeInTheDocument();
    expect(screen.getByText(/45 días corridos/i)).toBeInTheDocument();
  });

  test("shows source information when event has source", () => {
    const eventWithSource: EventResponse = {
      ...mockEvent,
      source_document_id: "doc-123",
      source_page: 4,
      source_fragment: "La adjudicación se realizará el 10 de septiembre",
    };

    render(<EventDetailModal event={eventWithSource} open={true} onClose={() => {}} />);

    expect(screen.getByText(/fuente en el documento/i)).toBeInTheDocument();
    expect(screen.getByText(/página 4/i)).toBeInTheDocument();
    expect(screen.getByText(/la adjudicación se realizará/i)).toBeInTheDocument();
  });

  test("calls onViewSource when source button is clicked", async () => {
    const user = userEvent.setup();
    const onViewSource = vi.fn();
    const eventWithSource: EventResponse = {
      ...mockEvent,
      source_document_id: "doc-123",
      source_page: 4,
    };

    render(
      <EventDetailModal
        event={eventWithSource}
        open={true}
        onClose={() => {}}
        onViewSource={onViewSource}
      />
    );

    const viewButton = screen.getByLabelText(/ver fuente en el pliego/i);
    await user.click(viewButton);

    expect(onViewSource).toHaveBeenCalledWith("doc-123", 4);
  });

  test("shows edit and close buttons for all events", () => {
    render(<EventDetailModal event={mockEvent} open={true} onClose={() => {}} />);

    expect(screen.getByRole("button", { name: /editar fecha/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cerrar/i })).toBeInTheDocument();
  });

  test("shows delete button only for user_input events", () => {
    const userInputEvent: EventResponse = {
      ...mockEvent,
      date_source: "user_input",
    };

    render(<EventDetailModal event={userInputEvent} open={true} onClose={() => {}} />);

    expect(screen.getByRole("button", { name: /eliminar/i })).toBeInTheDocument();
  });

  test("does not show delete button for detected events", () => {
    render(<EventDetailModal event={mockEvent} open={true} onClose={() => {}} />);

    expect(screen.queryByRole("button", { name: /eliminar/i })).not.toBeInTheDocument();
  });

  test("shows empty state when no deadlines or source", () => {
    render(<EventDetailModal event={mockEvent} open={true} onClose={() => {}} />);

    expect(
      screen.getByText(/este evento no tiene plazos dependientes ni fuente verificable/i)
    ).toBeInTheDocument();
  });

  test("does not render when open is false", () => {
    render(<EventDetailModal event={mockEvent} open={false} onClose={() => {}} />);

    expect(screen.queryByText("Adjudicación")).not.toBeInTheDocument();
  });

  test("shows pending date badge and message when event has no date", () => {
    const pendingEvent: EventResponse = {
      ...mockEvent,
      event_date: null,
      date_source: "pending",
    };

    render(<EventDetailModal event={pendingEvent} open={true} onClose={() => {}} />);

    expect(screen.getByText("Fecha pendiente")).toBeInTheDocument();
    expect(screen.getByText("Pendiente")).toBeInTheDocument();
  });

  test("edit button is present", () => {
    render(<EventDetailModal event={mockEvent} open={true} onClose={() => {}} />);

    const editButton = screen.getByRole("button", { name: /editar fecha/i });
    expect(editButton).toBeInTheDocument();
  });

  test("delete button is present for user_input events", () => {
    const userInputEvent: EventResponse = {
      ...mockEvent,
      date_source: "user_input",
    };

    render(<EventDetailModal event={userInputEvent} open={true} onClose={() => {}} />);

    const deleteButton = screen.getByRole("button", { name: /eliminar/i });
    expect(deleteButton).toBeInTheDocument();
  });
});
