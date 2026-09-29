import { render, screen } from "@testing-library/react";

import type { UploadedFile } from "../../types/upload";
import { Step3Confirmation } from "./Step3Confirmation";

vi.mock("../../hooks/useDocumentUpload", () => ({
  useDocumentUpload: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}));

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

describe("Step3Confirmation", () => {
  const baseFiles = [
    buildUploadedFile("anexo-a.pdf"),
    buildUploadedFile("pliego.pdf"),
    buildUploadedFile("anexo-b.pdf"),
  ];

  test("renderiza primero el archivo designado como principal", () => {
    render(
      <Step3Confirmation
        files={baseFiles}
        primaryIndex={1}
        onBack={() => undefined}
        onContinueToStart={() => undefined}
      />,
    );

    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("pliego.pdf");
    expect(items[0]).toHaveTextContent("Principal");
    expect(items[1]).toHaveTextContent("anexo-a.pdf");
    expect(items[1]).toHaveTextContent("Anexo");
    expect(items[2]).toHaveTextContent("anexo-b.pdf");
    expect(items[2]).toHaveTextContent("Anexo");
  });

  test("muestra campo de nombre de analisis", () => {
    render(
      <Step3Confirmation
        files={baseFiles}
        primaryIndex={1}
        onBack={() => undefined}
        onContinueToStart={() => undefined}
      />,
    );

    expect(screen.getByLabelText(/nombre del análisis/i)).toBeInTheDocument();
  });

  test("muestra todas las unidades de negocio del mockup", () => {
    render(
      <Step3Confirmation
        files={baseFiles}
        primaryIndex={1}
        onBack={() => undefined}
        onContinueToStart={() => undefined}
      />,
    );

    expect(screen.getByRole("button", { name: /cedi/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pi/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /wemox/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /vulps/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /korex/i })).toBeInTheDocument();
  });
});
