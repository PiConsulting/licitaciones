/**
 * Al abrir una fuente, el visor tiene que dejar la cita a la vista.
 *
 * Antes se apuntaba al `<mark>` del resaltado por texto y, si no había, al tope
 * de la página. Con el resaltado por coordenadas funcionando, `<mark>` ya no
 * existe: SIEMPRE se caía en la segunda rama y el visor quedaba en el tope de
 * la página. Una cita a 680 puntos de una página de 842 quedaba fuera de la
 * vista — el subrayado estaba bien puesto, pero había que buscarlo scrolleando
 * a mano. Es exactamente lo que reportó la usuaria: "está subrayado pero hago
 * click y se posiciona mal; si scrolleo manualmente la encuentro".
 */

import { act, render } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

const { pageMock } = vi.hoisted(() => ({ pageMock: vi.fn() }));

vi.mock("react-pdf", () => ({
  Page: (props: Record<string, unknown>) => {
    pageMock(props);
    return <div data-testid="react-pdf-page" />;
  },
}));

import { PDFPage } from "./PDFPage";

const REGION_ABAJO = { x: 57, y: 680, width: 480, height: 10 };
const REGION_ARRIBA = { x: 57, y: 400, width: 480, height: 10 };
const REGION_MUY_ARRIBA = { x: 57, y: 120, width: 480, height: 10 };

function crearContenedor(clientHeight = 600) {
  const container = document.createElement("div");
  Object.defineProperty(container, "clientHeight", { value: clientHeight, configurable: true });
  container.scrollTop = 0;
  container.getBoundingClientRect = () => ({ top: 0 }) as DOMRect;
  container.scrollTo = vi.fn(({ top }: ScrollToOptions = {}) => {
    container.scrollTop = top ?? 0;
  }) as unknown as typeof container.scrollTo;
  return container;
}

/** Renderiza la página y simula que react-pdf resolvió tamaño y text layer. */
function renderizarYCargar({
  regions,
  clientHeight = 600,
  isActivePage = true,
}: {
  regions: Array<{ x: number; y: number; width: number; height: number }>;
  clientHeight?: number;
  isActivePage?: boolean;
}) {
  pageMock.mockClear();
  const container = crearContenedor(clientHeight);
  const scrollContainerRef = { current: container };

  const { container: dom } = render(
    <PDFPage
      pageNumber={4}
      citationTexts={["La cita que se está verificando"]}
      sources={[{ page: 4, highlight_regions: regions }]}
      scrollContainerRef={scrollContainerRef}
      isActivePage={isActivePage}
    />,
  );

  // El wrapper de la página arranca en 0 dentro del contenedor.
  const wrapper = dom.querySelector("#pdf-page-4") as HTMLElement;
  wrapper.getBoundingClientRect = () => ({ top: 0 }) as DOMRect;

  const props = pageMock.mock.calls[0][0];
  // Escala efectiva 1: la página se renderiza a su tamaño nativo en puntos.
  act(() => {
    props.onLoadSuccess({ width: 600, originalWidth: 600, height: 842 });
    props.onRenderTextLayerSuccess();
  });

  return container;
}

describe("posicionamiento al abrir una fuente", () => {
  test("scrollea hasta la región del resaltado, no al tope de la página", () => {
    const container = renderizarYCargar({ regions: [REGION_ABAJO] });

    // y=680, menos el 30% de 600 de margen = 500.
    expect(container.scrollTop).toBe(500);
  });

  test("una cita cerca del tope no fuerza scroll negativo", () => {
    const container = renderizarYCargar({ regions: [REGION_MUY_ARRIBA] });

    expect(container.scrollTop).toBe(0);
  });

  test("con varias regiones apunta a la primera del texto, no a la última", () => {
    const container = renderizarYCargar({ regions: [REGION_ABAJO, REGION_ARRIBA] });

    // La cita empieza en y=400: hay que ver su comienzo, no su última línea.
    expect(container.scrollTop).toBe(220);
  });

  test("una página que no es la de la cita activa no scrollea", () => {
    const container = renderizarYCargar({ regions: [REGION_ABAJO], isActivePage: false });

    expect(container.scrollTop).toBe(0);
    expect(container.scrollTo).not.toHaveBeenCalled();
  });

  test("nunca scrollea la ventana", () => {
    const scrollWindow = vi.spyOn(window, "scrollTo").mockImplementation(() => {});

    renderizarYCargar({ regions: [REGION_ABAJO] });

    expect(scrollWindow).not.toHaveBeenCalled();
    scrollWindow.mockRestore();
  });
});
