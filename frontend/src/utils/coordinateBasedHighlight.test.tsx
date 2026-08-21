import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { HighlightOverlay, getCombinedHighlightRegions } from "./coordinateBasedHighlight";

/**
 * REGRESIÓN HL-01 (auditoría 2026-08-13): contrato de coordenadas.
 *
 * El backend emite las regiones con origen top-left, en puntos de la página
 * SIN escalar. Este overlay sólo debe multiplicar por la escala efectiva.
 *
 * Antes de HL-01 aplicaba `pageHeight - y - height` usando la altura YA
 * renderizada, lo que sólo daba el resultado correcto con scale === 1 y
 * mandaba el recuadro fuera de la página con scale < 1.
 */

function firstRegionStyle(container: HTMLElement): CSSStyleDeclaration {
  const overlay = container.firstElementChild as HTMLElement;
  const rect = overlay.firstElementChild as HTMLElement;
  return rect.style;
}

describe("HighlightOverlay - contrato de coordenadas (HL-01)", () => {
  const region = { x: 70, y: 120, width: 400, height: 30 };

  it("posiciona el recuadro en y * scale, sin invertir el eje", () => {
    const { container } = render(<HighlightOverlay regions={[region]} scale={1} />);
    const style = firstRegionStyle(container);

    expect(style.top).toBe("120px");
    expect(style.left).toBe("70px");
    expect(style.width).toBe("400px");
    expect(style.height).toBe("30px");
  });

  it("escala linealmente: un texto arriba sigue arriba en cualquier zoom", () => {
    for (const scale of [0.5, 0.75, 1, 1.25, 1.5, 2]) {
      const { container, unmount } = render(<HighlightOverlay regions={[region]} scale={scale} />);
      const style = firstRegionStyle(container);

      expect(style.top).toBe(`${120 * scale}px`);
      // Nunca fuera de la página por arriba (el bug viejo daba top negativo
      // con scale < 1).
      expect(Number.parseFloat(style.top)).toBeGreaterThan(0);
      unmount();
    }
  });

  it("mantiene el orden vertical: menor y se dibuja más arriba", () => {
    const arriba = { x: 70, y: 60, width: 100, height: 20 };
    const abajo = { x: 70, y: 700, width: 100, height: 20 };

    const { container } = render(<HighlightOverlay regions={[arriba, abajo]} scale={1.5} />);
    const overlay = container.firstElementChild as HTMLElement;
    const [first, second] = Array.from(overlay.children) as HTMLElement[];

    expect(Number.parseFloat(first.style.top)).toBeLessThan(Number.parseFloat(second.style.top));
  });

  it("no renderiza nada si no hay escala resuelta todavía", () => {
    const { container } = render(<HighlightOverlay regions={[region]} scale={0} />);
    expect(container.firstChild).toBeNull();
  });

  it("no renderiza nada si no hay regiones", () => {
    const { container } = render(<HighlightOverlay regions={[]} scale={1} />);
    expect(container.firstChild).toBeNull();
  });
});

describe("getCombinedHighlightRegions", () => {
  it("junta las regiones de la página pedida y deduplica idénticas", () => {
    const shared = { x: 1, y: 2, width: 3, height: 4 };
    const otra = { x: 9, y: 9, width: 9, height: 9 };

    const regions = getCombinedHighlightRegions(
      [
        { page: 1, highlight_regions: [shared] },
        { page: 1, highlight_regions: [{ ...shared }, otra] },
        { page: 2, highlight_regions: [{ x: 5, y: 5, width: 5, height: 5 }] },
        { page: 1 },
      ],
      1
    );

    expect(regions).toHaveLength(2);
    expect(regions).toEqual([shared, otra]);
  });
});
