import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { Step1UploadFiles } from "./Step1UploadFiles";

function createMockFile(name: string, type: string, size: number): File {
  const file = new File(["x"], name, { type });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

describe("Step1UploadFiles", () => {
  test("deshabilita Siguiente sin archivos", () => {
    render(<Step1UploadFiles onNext={() => undefined} />);

    expect(screen.getByRole("button", { name: /siguiente/i })).toBeDisabled();
  });

  test("habilita Siguiente cuando sube PDF válido", async () => {
    render(<Step1UploadFiles onNext={() => undefined} />);

    const input = screen.getByLabelText("Seleccionar archivos PDF");
    fireEvent.change(input, {
      target: { files: [createMockFile("ok.pdf", "application/pdf", 2 * 1024 * 1024)] },
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /siguiente/i })).toBeEnabled();
    });
  });

  test("muestra error por formato inválido", async () => {
    render(<Step1UploadFiles onNext={() => undefined} />);

    const input = screen.getByLabelText("Seleccionar archivos PDF");
    fireEvent.change(input, {
      target: {
        files: [
          createMockFile(
            "test.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            512,
          ),
        ],
      },
    });

    await waitFor(() => {
      expect(screen.getByText(/no es un PDF/i)).toBeInTheDocument();
    });
  });

  test("permite remover archivo de la lista", async () => {
    render(<Step1UploadFiles onNext={() => undefined} />);

    const input = screen.getByLabelText("Seleccionar archivos PDF");
    fireEvent.change(input, {
      target: { files: [createMockFile("test.pdf", "application/pdf", 1024)] },
    });

    await waitFor(() => {
      expect(screen.getByText("test.pdf")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText(/remover test.pdf/i));
    expect(screen.queryByText("test.pdf")).not.toBeInTheDocument();
  });

  test("muestra error cuando supera cantidad máxima", async () => {
    render(<Step1UploadFiles onNext={() => undefined} />);

    const files = Array.from({ length: 11 }, (_, index) =>
      createMockFile(`file-${index}.pdf`, "application/pdf", 1024),
    );

    const input = screen.getByLabelText("Seleccionar archivos PDF");
    fireEvent.change(input, { target: { files } });

    await waitFor(() => {
      expect(screen.getByText(/podés subir hasta 10 archivos/i)).toBeInTheDocument();
    });
  });
});
