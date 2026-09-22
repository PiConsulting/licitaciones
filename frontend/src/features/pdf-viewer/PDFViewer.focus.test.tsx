/**
 * El visor tiene que enfocar la cita al abrir una fuente.
 *
 * Dos bugs distintos, encontrados en la misma sesión:
 *
 * 1. El código de enfoque leía `pdfContainerRef.current`, pero
 *    `useContainerWidth` devuelve un CALLBACK ref -- una función. `.current`
 *    sobre una función es `undefined`, así que el contenedor siempre resultaba
 *    nulo, la rutina salía por el `return` temprano y el visor NUNCA
 *    scrolleaba. TypeScript no lo detectó porque `ref` es genérico, y los tests
 *    de la pieza de scroll no lo detectaban porque le inyectaban un objeto ref
 *    de verdad.
 *
 * 2. El enfoque se aplicaba UNA sola vez, apenas cambiaba la página. El visor
 *    renderiza una ventana de páginas y las que están arriba de la objetivo
 *    crecen a medida que cargan, empujándola hacia abajo: la posición calculada
 *    dejaba de ser la correcta medio segundo después.
 *
 * Estos tests son a nivel del visor completo, que es donde los dos se ven.
 */

import { act, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, test, vi } from "vitest";

const { pageProps } = vi.hoisted(() => ({ pageProps: [] as Record<string, unknown>[] }));

/** Cada `scrollTo` que recibe el panel del PDF, en orden. */
const scrollCalls: number[] = [];

vi.mock("../../utils/pdfWorker", () => ({}));

vi.mock("react-pdf", () => ({
  pdfjs: { GlobalWorkerOptions: {} },
  Document: ({ children, onLoadSuccess }: Record<string, unknown>) => {
    // El documento tiene 10 páginas.
    (onLoadSuccess as (info: { numPages: number }) => void)?.({ numPages: 10 });
    return <div data-testid="pdf-document">{children as never}</div>;
  },
  Page: (props: Record<string, unknown>) => {
    pageProps.push(props);
    return <div data-testid={`page-${props.pageNumber}`} />;
  },
}));

vi.mock("./hooks/useSASUrl", () => ({
  useSASUrl: () => ({ data: { url: "https://example/doc.pdf" }, isLoading: false, refetch: vi.fn() }),
}));

import { PDFViewer } from "./PDFViewer";

const DOC = "doc-1";
const CITA = {
  document_id: DOC,
  page: 6,
  text: "El plazo de entrega será de noventa (90) días corridos",
  document_name: "Pliego.pdf",
};
const SOURCE = {
  id: 0,
  document_id: DOC,
  document_name: "Pliego.pdf",
  page: 6,
  text: CITA.text,
  highlight_regions: [{ x: 57, y: 680, width: 480, height: 10 }],
};

/** Simula el layout: el panel scrollea, y cada página mide 900px de alto una
 * vez renderizada (antes de eso, 0). */
function prepararLayout(alturaDePaginaRenderizada = 900) {
  const rendered = new Set<number>();
  scrollCalls.length = 0;

  HTMLElement.prototype.scrollTo = function (this: HTMLElement, options?: ScrollToOptions) {
    if (this.dataset.testid === "pdf-container") {
      scrollCalls.push(options?.top ?? 0);
      this.scrollTop = options?.top ?? 0;
    }
  } as never;

  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    get(this: HTMLElement) {
      return this.dataset.testid === "pdf-container" ? 600 : 0;
    },
  });

  HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
    if (this.dataset.testid === "pdf-container") {
      return { top: 0 } as DOMRect;
    }
    const match = /^pdf-page-(\d+)$/.exec(this.id ?? "");
    if (match) {
      const page = Number(match[1]);
      // Cada página anterior YA renderizada aporta su alto.
      let top = 0;
      for (let previous = 1; previous < page; previous += 1) {
        top += rendered.has(previous) ? alturaDePaginaRenderizada : 0;
      }
      const container = document.querySelector('[data-testid="pdf-container"]') as HTMLElement | null;
      return { top: top - (container?.scrollTop ?? 0) } as DOMRect;
    }
    return { top: 0 } as DOMRect;
  } as never;

  return rendered;
}

function renderizar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PDFViewer
        documentId={DOC}
        documentName="Pliego.pdf"
        citations={[CITA]}
        documents={[{ id: DOC, filename: "Pliego.pdf", page_count: 10, file_size_bytes: 1, is_primary: true }]}
        focusCitation={CITA}
        sources={[SOURCE]}
      />
    </QueryClientProvider>,
  );
}

/** Una cita a 40 puntos del tope de la página 2: el caso reportado. */
function renderizarConCitaEnLaPagina2() {
  const cita = { ...CITA, page: 2, text: "La Municipalidad de Rosario llama a Licitación Privada" };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PDFViewer
        documentId={DOC}
        documentName="Pliego.pdf"
        citations={[cita]}
        documents={[{ id: DOC, filename: "Pliego.pdf", page_count: 10, file_size_bytes: 1, is_primary: true }]}
        focusCitation={cita}
        sources={[
          {
            ...SOURCE,
            page: 2,
            text: cita.text,
            highlight_regions: [{ x: 57, y: 40, width: 480, height: 10 }],
          },
        ]}
      />
    </QueryClientProvider>,
  );
}

/** Un ítem con DOS citas propias en la misma página (ej. un plazo de
 * "Plazos Clave" con una cita para el plazo y otra para el lugar de entrega,
 * caso real documentado en el FIX 2026-09-03 de `PDFViewer.tsx`) -- el
 * usuario enfoca la SEGUNDA (más abajo en la página). El caso reportado:
 * el visor scrolleaba a la PRIMERA (más arriba) sin importar cuál se había
 * clickeado, porque el cálculo de la posición de scroll tomaba el mínimo
 * entre las dos, no la de la cita realmente enfocada. */
function renderizarConDosCitasEnLaMismaPagina() {
  const citaArriba = { ...CITA, text: "El plazo de entrega será de noventa (90) días corridos" };
  const citaAbajo = {
    ...CITA,
    text: "Las entregas se realizarán en el 3er piso del Palacio Municipal",
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PDFViewer
        documentId={DOC}
        documentName="Pliego.pdf"
        citations={[citaArriba, citaAbajo]}
        documents={[{ id: DOC, filename: "Pliego.pdf", page_count: 10, file_size_bytes: 1, is_primary: true }]}
        focusCitation={citaAbajo}
        sources={[
          { ...SOURCE, text: citaArriba.text, highlight_regions: [{ x: 57, y: 100, width: 480, height: 10 }] },
          { ...SOURCE, text: citaAbajo.text, highlight_regions: [{ x: 57, y: 680, width: 480, height: 10 }] },
        ]}
      />
    </QueryClientProvider>,
  );
}

function contenedor(): HTMLElement {
  return screen.getByTestId("pdf-container");
}

function simularRender(pageNumber: number, rendered: Set<number>) {
  const props = pageProps.filter((p) => p.pageNumber === pageNumber).at(-1);
  if (!props) {
    return;
  }
  rendered.add(pageNumber);
  act(() => {
    (props.onLoadSuccess as (p: unknown) => void)?.({ width: 600, originalWidth: 600, height: 900 });
    (props.onRendered as (n: number) => void)?.(pageNumber);
  });
}

describe("enfoque de la cita en el visor", () => {
  beforeEach(() => {
    pageProps.length = 0;
  });

  test("el panel se scrollea al abrir la fuente (el contenedor no es nulo)", () => {
    const rendered = prepararLayout();
    renderizar();

    simularRender(6, rendered);

    expect(scrollCalls.length).toBeGreaterThan(0);
  });

  test("enfoca la región del resaltado, no el tope de la página", () => {
    const rendered = prepararLayout();
    renderizar();

    // Se renderizan primero todas las páginas de arriba, así la 6 ya está en
    // su posición final (5 páginas x 900px = 4500).
    [1, 2, 3, 4, 5, 6].forEach((page) => simularRender(page, rendered));

    // 4500 (páginas de arriba) + 680 (y de la cita) - 90 (15% de 600) = 5090.
    expect(scrollCalls.at(-1)).toBe(5090);
  });

  test("una cita cerca del tope de su página no abre en la anterior", () => {
    const rendered = prepararLayout();
    renderizarConCitaEnLaPagina2();

    [1, 2].forEach((page) => simularRender(page, rendered));

    // La página 2 arranca en 900. El destino no puede caer dentro de la 1.
    expect(scrollCalls.at(-1)).toBeGreaterThanOrEqual(900);
  });

  test("vuelve a enfocar cuando termina de renderizar una página de arriba", () => {
    const rendered = prepararLayout();
    renderizar();

    simularRender(6, rendered);
    const primeras = scrollCalls.length;
    const primerDestino = scrollCalls.at(-1);

    // Ahora termina la página 5, que estaba arriba: la 6 se corrió 900px.
    simularRender(5, rendered);

    expect(scrollCalls.length).toBeGreaterThan(primeras);
    expect(scrollCalls.at(-1)).not.toBe(primerDestino);
  });

  test("deja de reenfocar cuando ya no queda ninguna página anterior pendiente", () => {
    const rendered = prepararLayout();
    renderizar();

    [1, 2, 3, 4, 5, 6].forEach((page) => simularRender(page, rendered));
    const total = scrollCalls.length;

    // Las páginas de ABAJO no mueven a la objetivo: no hay por qué reenfocar.
    [7, 8].forEach((page) => simularRender(page, rendered));

    expect(scrollCalls.length).toBe(total);
  });

  test("con dos citas propias en la misma página, enfoca la región de la cita clickeada, no el mínimo entre ambas", () => {
    const rendered = prepararLayout();
    renderizarConDosCitasEnLaMismaPagina();

    [1, 2, 3, 4, 5, 6].forEach((page) => simularRender(page, rendered));

    // 4500 (páginas de arriba) + 680 (y de la cita de ABAJO, la clickeada) - 90 = 5090.
    // Antes del fix daba 4510 (usando el y=100 de la cita de ARRIBA, no clickeada).
    expect(scrollCalls.at(-1)).toBe(5090);
  });

  test("nunca scrollea la ventana", () => {
    const rendered = prepararLayout();
    const scrollWindow = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
    renderizar();

    [1, 2, 3, 4, 5, 6].forEach((page) => simularRender(page, rendered));

    expect(scrollWindow).not.toHaveBeenCalled();
    scrollWindow.mockRestore();
  });

});
