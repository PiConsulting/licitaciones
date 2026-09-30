import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, test, vi } from "vitest";

vi.mock("../../utils/pdfWorker", () => ({}));

vi.mock("react-pdf", () => ({
  pdfjs: { GlobalWorkerOptions: {} },
  Document: ({ children, onLoadSuccess }: Record<string, unknown>) => {
    (onLoadSuccess as (info: { numPages: number }) => void)?.({ numPages: 3 });
    return <div data-testid="pdf-document">{children as never}</div>;
  },
  Page: (props: Record<string, unknown>) => (
    <div
      className="react-pdf__Page"
      data-page-number={String(props.pageNumber)}
      data-scale={props.scale === undefined ? "" : String(props.scale)}
      data-testid={props.className === "shadow" ? `pdf-page-${String(props.pageNumber)}` : undefined}
    />
  ),
}));

vi.mock("./hooks/useSASUrl", () => ({
  useSASUrl: () => ({ data: { url: "https://example/doc.pdf" }, isLoading: false, refetch: vi.fn() }),
}));

import { PDFViewer } from "./PDFViewer";

function renderViewer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const citations = [{ document_id: "doc-1", page: 1, text: "Texto", document_name: "Pliego.pdf" }];

  return render(
    <QueryClientProvider client={client}>
      <PDFViewer
        documentId="doc-1"
        documentName="Pliego.pdf"
        citations={citations}
        documents={[{ id: "doc-1", filename: "Pliego.pdf", is_primary: true }]}
        focusCitation={citations[0]}
      />
    </QueryClientProvider>,
  );
}

describe("PDFViewer lupa", () => {
  test("arranca desactivada y el botón la activa y desactiva", async () => {
    const user = userEvent.setup();
    renderViewer();

    const button = screen.getByRole("button", { name: "Lupa" });
    expect(button).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    await user.click(button);

    expect(button).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("status")).toHaveTextContent("Modo lupa 2× · Esc para salir");

    await user.click(button);

    expect(button).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  test("la tecla L activa la lupa y Esc la desactiva", async () => {
    const user = userEvent.setup();
    renderViewer();

    await user.keyboard("l");
    expect(screen.getByRole("status")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  test("la tecla L se ignora mientras se escribe en un campo de texto", async () => {
    const user = userEvent.setup();
    render(<input aria-label="comentario" />);
    renderViewer();

    await user.click(screen.getByLabelText("comentario"));
    await user.keyboard("l");

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  test("el menú permite elegir aumento, forma y tamaño", async () => {
    const user = userEvent.setup();
    renderViewer();

    await user.click(screen.getByRole("button", { name: "Lupa" }));
    await user.click(screen.getByRole("button", { name: "Opciones de lupa" }));

    await user.click(screen.getByRole("button", { name: "3×" }));
    expect(screen.getByRole("status")).toHaveTextContent("Modo lupa 3×");
    expect(screen.getByRole("button", { name: "3×" })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "Círculo" }));
    expect(screen.getByRole("button", { name: "Círculo" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Franja" })).toHaveAttribute("aria-pressed", "false");

    await user.click(screen.getByRole("button", { name: "L" }));
    expect(screen.getByRole("button", { name: "L" })).toHaveAttribute("aria-pressed", "true");
  });

  test("Ctrl + rueda cambia el aumento sin tocar el zoom de la página", async () => {
    const user = userEvent.setup();
    renderViewer();

    await user.click(screen.getByRole("button", { name: "Lupa" }));
    const container = screen.getByTestId("pdf-container");

    fireEvent.wheel(container, { ctrlKey: true, deltaY: -100 });
    expect(screen.getByRole("status")).toHaveTextContent("Modo lupa 3×");

    fireEvent.wheel(container, { ctrlKey: true, deltaY: 100 });
    fireEvent.wheel(container, { ctrlKey: true, deltaY: 100 });
    expect(screen.getByRole("status")).toHaveTextContent("Modo lupa 1.5×");
  });

  test("la ventana de aumento aparece sobre la página y se oculta al salir", async () => {
    const user = userEvent.setup();
    renderViewer();

    await user.click(screen.getByRole("button", { name: "Lupa" }));
    expect(screen.queryByTestId("pdf-lens")).not.toBeInTheDocument();

    const page = screen.getByTestId("pdf-page-1");
    fireEvent.mouseMove(page, { clientX: 40, clientY: 30 });

    await waitFor(() => {
      expect(screen.getByTestId("pdf-lens")).toBeInTheDocument();
    });

    fireEvent.mouseLeave(screen.getByTestId("pdf-container"));

    await waitFor(() => {
      expect(screen.queryByTestId("pdf-lens")).not.toBeInTheDocument();
    });
  });

  test("el botón de pantalla completa abre el visor en un modal y Esc lo cierra", async () => {
    const user = userEvent.setup();
    renderViewer();

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Pantalla completa" }));

    const dialog = screen.getByRole("dialog", { name: "PDF a pantalla completa" });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Pantalla completa" })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Lupa" })).toBeInTheDocument();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("el modal abre al 100% mientras el visor en panel sigue ajustado al ancho", async () => {
    const user = userEvent.setup();
    renderViewer();

    expect(screen.getByTestId("pdf-page-1")).toHaveAttribute("data-scale", "");

    await user.click(screen.getByRole("button", { name: "Pantalla completa" }));

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByTestId("pdf-page-1")).toHaveAttribute("data-scale", "1");
  });

  test("el botón cerrar del modal vuelve al visor", async () => {
    const user = userEvent.setup();
    renderViewer();

    await user.click(screen.getByRole("button", { name: "Pantalla completa" }));
    await user.click(screen.getByRole("button", { name: "Cerrar pantalla completa" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("dentro del modal Esc primero apaga la lupa y después cierra el modal", async () => {
    const user = userEvent.setup();
    renderViewer();

    await user.click(screen.getByRole("button", { name: "Pantalla completa" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Lupa" }));
    expect(within(dialog).getByRole("status")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(within(dialog).queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("el modal abre en la página donde estaba el visor y cambia de página sin afectar al visor", async () => {
    const user = userEvent.setup();
    renderViewer();

    await user.click(screen.getByRole("button", { name: "Página siguiente" }));
    expect(screen.getByText(/Pág\.\s*2\s*\/\s*3/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Pantalla completa" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/Pág\.\s*2\s*\/\s*3/)).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Página siguiente" }));
    expect(within(dialog).getByText(/Pág\.\s*3\s*\/\s*3/)).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Página anterior" }));
    await user.click(within(dialog).getByRole("button", { name: "Página anterior" }));
    expect(within(dialog).getByText(/Pág\.\s*1\s*\/\s*3/)).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Cerrar pantalla completa" }));
    expect(screen.getByText(/Pág\.\s*2\s*\/\s*3/)).toBeInTheDocument();
  });
});
