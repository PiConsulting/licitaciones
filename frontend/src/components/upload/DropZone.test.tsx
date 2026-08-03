import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { DropZone } from "./DropZone";

let dragActive = false;
let capturedOnDrop: ((acceptedFiles: File[], rejections: Array<{ file: File }>) => void) | null = null;

vi.mock("react-dropzone", () => ({
  useDropzone: ({ onDrop }: { onDrop: (acceptedFiles: File[], rejections: Array<{ file: File }>) => void }) => {
    capturedOnDrop = onDrop;
    return {
      getRootProps: () => ({}),
      getInputProps: () => ({
        onChange: (event: { target: { files?: File[] | FileList | null } }) => {
          const files = Array.from(event.target.files ?? []);
          onDrop(files, []);
        },
        "aria-label": "Seleccionar archivos PDF",
      }),
      isDragActive: dragActive,
    };
  },
}));

describe("DropZone", () => {
  test("renderiza estado inicial", () => {
    dragActive = false;
    render(<DropZone onFilesSelected={() => undefined} />);

    expect(screen.getByText(/arrastrá tus pdfs acá/i)).toBeInTheDocument();
    expect(screen.getByTestId("upload-icon")).toBeInTheDocument();
  });

  test("aplica estilos de dragover", () => {
    dragActive = true;
    render(<DropZone onFilesSelected={() => undefined} />);

    const dropzone = screen.getByTestId("dropzone");
    expect(dropzone.className).toContain("border-primary");
  });

  test("dispara onFilesSelected cuando se seleccionan archivos", async () => {
    dragActive = false;
    const onFilesSelected = vi.fn();
    render(<DropZone onFilesSelected={onFilesSelected} />);

    const file = new File(["x"], "test.pdf", { type: "application/pdf" });
    capturedOnDrop?.([file], []);

    await waitFor(() => {
      expect(onFilesSelected).toHaveBeenCalled();
    });
  });
});
