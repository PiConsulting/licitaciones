import config from "../tailwind.config.js";

describe("Tailwind config CEDI", () => {
  test("expone tokens de color del DS", () => {
    const colors = config.theme?.extend?.colors as Record<string, unknown>;
    const cedi = colors.cedi as Record<string, string>;

    expect(cedi.celeste).toBe("#0099DB");
    expect(cedi.navy).toBe("#003C6B");
    expect(cedi.electric).toBe("#2F4EF8");
    expect(cedi.violet).toBe("#A966FF");
    expect(cedi.mint).toBe("#7FF3DE");
  });

  // Los gradientes NO pueden vivir en `colors` -- un gradiente no es un valor
  // válido para `background-color` (el navegador lo descarta en silencio, el
  // botón queda sin fondo pero clickeable). Tienen que ir en `backgroundImage`
  // para que `bg-cedi-gradient-*` genere `background-image`, no `background-color`.
  test("expone los gradientes del DS vía backgroundImage, no colors", () => {
    const backgroundImage = config.theme?.extend?.backgroundImage as Record<string, string>;

    expect(backgroundImage["cedi-gradient-button"]).toBe("linear-gradient(90deg,#2F4EF8,#A966FF)");
    expect(backgroundImage["cedi-gradient-progress"]).toBe("linear-gradient(90deg,#0099DB,#7FF3DE)");
    expect(backgroundImage["cedi-gradient-icon"]).toBe("linear-gradient(145deg,#0099DB,#2F4EF8)");
    expect(backgroundImage["cedi-gradient-accent"]).toBe(
      "linear-gradient(90deg,#0099DB,#2F4EF8,#A966FF)",
    );

    const colors = config.theme?.extend?.colors as Record<string, unknown>;
    const cedi = colors.cedi as Record<string, string>;
    expect(cedi["gradient-button"]).toBeUndefined();
  });

  test("registra tipografias display/body CEDI", () => {
    const fontFamily = config.theme?.extend?.fontFamily as Record<string, string[]>;

    expect(fontFamily.display[0]).toBe("Space Grotesk");
    expect(fontFamily.body[0]).toBe("Montserrat");
  });
});
