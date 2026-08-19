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
  test("renderiza primero el archivo designado como principal", () => {
    const files = [
      buildUploadedFile("anexo-a.pdf"),
      buildUploadedFile("pliego.pdf"),
      buildUploadedFile("anexo-b.pdf"),
    ];

    render(
      <Step3Confirmation
        files={files}
        primaryIndex={1}
        onBack={() => undefined}
        onContinueToStart={() => undefined}
      />,
    );

    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("pliego.pdf (Principal)");
    expect(items[1]).toHaveTextContent("anexo-a.pdf");
    expect(items[2]).toHaveTextContent("anexo-b.pdf");
  });
});
