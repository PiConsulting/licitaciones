/**
 * El visor scrollea SU panel, nunca la ventana.
 *
 * `Element.scrollIntoView()` scrollea todos los ancestros scrolleables del
 * elemento, incluido el documento. El visor lo usaba en dos lugares, así que
 * cada click en una fuente acomodaba el panel del PDF y de paso arrastraba la
 * página entera del navegador hacia abajo. Con una lista de diez ítems, diez
 * clicks eran diez saltos.
 */

import { describe, expect, test, vi } from "vitest";

import {
  focusIsStillPending,
  focusScrollTop,
  offsetWithinContainer,
  scrollContainerTo,
} from "./scrollWithinContainer";

function crearContenedor({
  clientHeight = 600,
  scrollTop = 0,
  containerTop = 100,
}: { clientHeight?: number; scrollTop?: number; containerTop?: number } = {}) {
  const container = document.createElement("div");
  Object.defineProperty(container, "clientHeight", { value: clientHeight, configurable: true });
  container.scrollTop = scrollTop;
  container.getBoundingClientRect = () => ({ top: containerTop }) as DOMRect;
  container.scrollTo = vi.fn(({ top }: ScrollToOptions = {}) => {
    container.scrollTop = top ?? 0;
  }) as unknown as typeof container.scrollTo;
  return container;
}

function crearElemento(top: number) {
  const element = document.createElement("div");
  element.getBoundingClientRect = () => ({ top }) as DOMRect;
  return element;
}

describe("offsetWithinContainer", () => {
  test("mide desde el tope del CONTENIDO, no desde el viewport", () => {
    const container = crearContenedor({ containerTop: 100, scrollTop: 250 });
    const element = crearElemento(180);

    // El elemento está 80px por debajo del borde visible del contenedor, y el
    // contenedor ya está scrolleado 250px: su posición real en el contenido es 330.
    expect(offsetWithinContainer(container, element)).toBe(330);
  });

  test("un elemento en el borde superior con scroll en cero da 0", () => {
    const container = crearContenedor({ containerTop: 100, scrollTop: 0 });

    expect(offsetWithinContainer(container, crearElemento(100))).toBe(0);
  });
});

describe("scrollContainerTo", () => {
  test("mueve el scroll del contenedor y nada más", () => {
    const container = crearContenedor({ clientHeight: 600 });
    const scrollWindow = vi.spyOn(window, "scrollTo").mockImplementation(() => {});

    scrollContainerTo(container, 820);

    expect(container.scrollTop).toBe(820);
    expect(scrollWindow).not.toHaveBeenCalled();
    scrollWindow.mockRestore();
  });

  test("nunca scrollea a un valor negativo", () => {
    const container = crearContenedor({ clientHeight: 600 });

    scrollContainerTo(container, -50);

    expect(container.scrollTop).toBe(0);
  });

  test("funciona sin scrollTo con opciones (jsdom, navegadores viejos)", () => {
    const container = crearContenedor({ clientHeight: 600 });
    // @ts-expect-error se elimina a propósito para probar el camino de respaldo
    container.scrollTo = undefined;

    scrollContainerTo(container, 820);

    expect(container.scrollTop).toBe(820);
  });
});

describe("focusScrollTop", () => {
  const VIEWPORT = 800;

  test("una cita cerca del tope de su página NO muestra la página anterior", () => {
    // La página 2 arranca en 900; la cita está a 60 puntos de su tope.
    // Con el margen viejo (30% de 800 = 240) el resultado era 720: dentro de la
    // página 1, la portada.
    const top = focusScrollTop({ pageOffset: 900, regionTop: 60, scale: 1, viewportHeight: VIEWPORT });

    expect(top).toBeGreaterThanOrEqual(900);
  });

  test("una cita en el medio de la página deja algo de contexto arriba", () => {
    const top = focusScrollTop({ pageOffset: 900, regionTop: 600, scale: 1, viewportHeight: VIEWPORT });

    expect(top).toBe(900 + 600 - 96);
    expect(top).toBeLessThan(900 + 600);
  });

  test("el margen está acotado: no crece con la altura del panel", () => {
    const chico = focusScrollTop({ pageOffset: 0, regionTop: 600, scale: 1, viewportHeight: 400 });
    const enorme = focusScrollTop({ pageOffset: 0, regionTop: 600, scale: 1, viewportHeight: 2000 });

    expect(chico).toBe(600 - 60); // 15% de 400
    expect(enorme).toBe(600 - 96); // tope de 96px, no 300
  });

  test("sin coordenadas se enfoca el tope de la página", () => {
    const top = focusScrollTop({ pageOffset: 900, regionTop: null, scale: 1, viewportHeight: VIEWPORT });

    expect(top).toBe(900);
  });

  test("la coordenada se escala igual que la página renderizada", () => {
    const top = focusScrollTop({ pageOffset: 0, regionTop: 600, scale: 0.5, viewportHeight: VIEWPORT });

    expect(top).toBe(300 - 96);
  });
});

describe("focusIsStillPending", () => {
  test("hay que reenfocar mientras falte una página de ARRIBA", () => {
    expect(focusIsStillPending([1, 2, 3, 4], 3, new Set([3]))).toBe(true);
  });

  test("las páginas de abajo no mueven a la objetivo", () => {
    expect(focusIsStillPending([1, 2, 3, 4], 3, new Set([1, 2, 3]))).toBe(false);
  });
});
