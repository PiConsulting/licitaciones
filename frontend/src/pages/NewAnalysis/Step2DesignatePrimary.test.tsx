import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { UploadedFile } from "../../types/upload";
import { Step2DesignatePrimary } from "./Step2DesignatePrimary";

function buildUploadedFile(name: string): UploadedFile {
  const file = new File(["x"], name, { type: "application/pdf" });
  return {
    id: `${name}-id`,
    file,
    sizeMb: "1.00",
    pagesLabel: "N/D páginas",
    status: "valid",
  };
}

describe("Step2DesignatePrimary", () => {
  test("auto-designa y avanza cuando hay un solo archivo", async () => {
    const onNext = vi.fn();

    render(
      <Step2DesignatePrimary files={[buildUploadedFile("single.pdf")]} onBack={() => undefined} onNext={onNext} />,
    );

    await waitFor(() => {
      expect(onNext).toHaveBeenCalledWith(0);
    });
  });

  test("requiere selección manual con múltiples archivos", () => {
    const onNext = vi.fn();

    render(
      <Step2DesignatePrimary
        files={[buildUploadedFile("a.pdf"), buildUploadedFile("b.pdf")]}
        onBack={() => undefined}
        onNext={onNext}
      />,
    );

    const nextButton = screen.getByRole("button", { name: /siguiente/i });
    expect(nextButton).toBeDisabled();
    expect(screen.queryByText("Seleccioná cuál es el pliego principal")).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/a.pdf/i));
    expect(nextButton).toBeEnabled();
  });
});
