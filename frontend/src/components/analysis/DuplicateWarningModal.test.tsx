import { fireEvent, render, screen } from "@testing-library/react";

import { DuplicateWarningModal } from "./DuplicateWarningModal";

describe("DuplicateWarningModal", () => {
  const duplicates = [
    {
      document_id: "doc-1",
      filename: "pliego.pdf",
      existing_analysis_id: "analysis-123",
      created_at: "2026-08-01T10:00:00Z",
      created_by: "juan@example.com",
      status: "completed" as const,
    },
  ];

  test("muestra opciones y confirma decisiones", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();

    render(<DuplicateWarningModal duplicates={duplicates} onConfirm={onConfirm} onCancel={onCancel} />);

    expect(screen.getByText(/Documentos ya analizados/i)).toBeInTheDocument();

    const select = screen.getByRole("combobox");
    expect(select).toBeInTheDocument();
    expect(screen.getAllByRole("option")).toHaveLength(3);

    fireEvent.change(select, { target: { value: "analyze_again" } });
    fireEvent.click(screen.getByRole("button", { name: /Confirmar decisiones/i }));

    expect(onConfirm).toHaveBeenCalledWith([
      {
        document_id: "doc-1",
        action: "analyze_again",
      },
    ]);

    fireEvent.click(screen.getByRole("button", { name: /^Cerrar$/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
