import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, test, vi } from "vitest";

const { pageProps } = vi.hoisted(() => ({ pageProps: [] as Record<string, unknown>[] }));

vi.mock("../../utils/pdfWorker", () => ({}));

vi.mock("react-pdf", () => ({
  pdfjs: { GlobalWorkerOptions: {} },
  Document: ({ children, onLoadSuccess }: Record<string, unknown>) => {
    (onLoadSuccess as (info: { numPages: number }) => void)?.({ numPages: 20 });
    return <div data-testid="pdf-document">{children as never}</div>;
  },
  Page: (props: Record<string, unknown>) => {
    pageProps.push(props);
    return <div data-testid={`pdf-page-${String(props.pageNumber)}`} />;
  },
}));

vi.mock("./hooks/useSASUrl", () => ({
  useSASUrl: () => ({ data: { url: "https://example/doc.pdf" }, isLoading: false, refetch: vi.fn() }),
}));

import { PDFViewer } from "./PDFViewer";

function renderViewer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  const citations = [
    { document_id: "doc-1", page: 5, text: "Texto de pliego", document_name: "Pliego Principal.pdf" },
    { document_id: "doc-2", page: 2, text: "Texto de anexo", document_name: "Anexo I.pdf" },
  ];

  return render(
    <QueryClientProvider client={client}>
      <PDFViewer
        documentId="doc-1"
        documentName="Pliego Principal.pdf"
        citations={citations}
        documents={[
          { id: "doc-1", filename: "Pliego Principal.pdf", is_primary: true },
          { id: "doc-2", filename: "Anexo I.pdf", is_primary: false },
        ]}
        focusCitation={citations[0]}
      />
    </QueryClientProvider>,
  );
}

function renderViewerWithNonSourceDocument() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  const citations = [
    { document_id: "doc-1", page: 5, text: "Texto de pliego", document_name: "Pliego Principal.pdf" },
  ];

  return render(
    <QueryClientProvider client={client}>
      <PDFViewer
        documentId="doc-1"
        documentName="Pliego Principal.pdf"
        citations={citations}
        documents={[
          { id: "doc-1", filename: "Pliego Principal.pdf", is_primary: true },
          { id: "doc-3", filename: "Anexo II.pdf", is_primary: false },
        ]}
        focusCitation={citations[0]}
      />
    </QueryClientProvider>,
  );
}

describe("PDFViewer selector de documentos", () => {
  beforeEach(() => {
    pageProps.length = 0;
  });

  test("muestra un select con los documentos y el activo seleccionado", async () => {
    renderViewer();

    const select = await screen.findByRole("combobox", { name: "Documento" });
    expect(select).toHaveValue("doc-1");
    expect(screen.getByRole("option", { name: "Pliego Principal.pdf" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Anexo I.pdf" })).toBeInTheDocument();
  });

  test("recuerda la ultima pagina por documento al alternar en el select", async () => {
    const user = userEvent.setup();
    renderViewer();

    expect(await screen.findByText((text) => /Página\s*5\s*de\s*20/.test(text))).toBeInTheDocument();

    const select = screen.getByRole("combobox", { name: "Documento" });

    await user.selectOptions(select, "doc-2");
    expect(screen.getByText((text) => /Página\s*2\s*de\s*20/.test(text))).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Página siguiente" }));
    await user.click(screen.getByRole("button", { name: "Página siguiente" }));
    expect(screen.getByText((text) => /Página\s*4\s*de\s*20/.test(text))).toBeInTheDocument();

    await user.selectOptions(select, "doc-1");
    expect(screen.getByText((text) => /Página\s*5\s*de\s*20/.test(text))).toBeInTheDocument();

    await user.selectOptions(select, "doc-2");
    expect(screen.getByText((text) => /Página\s*4\s*de\s*20/.test(text))).toBeInTheDocument();
  });

  test("no subraya texto al abrir un documento sin fuente activa", async () => {
    const user = userEvent.setup();
    renderViewerWithNonSourceDocument();

    const select = screen.getByRole("combobox", { name: "Documento" });
    await user.selectOptions(select, "doc-3");

    await user.click(screen.getByRole("button", { name: "Página siguiente" }));
    await user.click(screen.getByRole("button", { name: "Página siguiente" }));
    await user.click(screen.getByRole("button", { name: "Página siguiente" }));
    await user.click(screen.getByRole("button", { name: "Página siguiente" }));

    const pageFiveProps = pageProps.filter((props) => props.pageNumber === 5).at(-1);
    expect(pageFiveProps).toBeDefined();
    expect(pageFiveProps?.customTextRenderer).toBeUndefined();
  });
});
