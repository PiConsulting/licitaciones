import { createCitationTextRenderer, isPartOfCitation } from "./highlightText";

describe("isPartOfCitation", () => {
  test("detecta un fragmento contenido en la cita, sin importar mayúsculas/espacios", () => {
    expect(isPartOfCitation("Objeto", ["El objeto de la  licitación es..."])).toBe(true);
  });

  test("no marca match para fragmentos muy cortos (ruido)", () => {
    expect(isPartOfCitation("de", ["El objeto de la licitación"])).toBe(false);
  });

  test("no marca match para stopwords de 3-5 letras muy frecuentes (ruido)", () => {
    // Antes el piso era 3 caracteres: "los", "las", "del", "por", "con", "una"
    // matcheaban casi cualquier cita y resaltaban palabras sueltas por toda la
    // página, sin relación real con el fragmento citado.
    const citation = "Los oferentes deberán presentar la garantía dentro del plazo establecido";
    expect(isPartOfCitation("los", [citation])).toBe(false);
    expect(isPartOfCitation("del", [citation])).toBe(false);
    expect(isPartOfCitation("la", [citation])).toBe(false);
  });

  test("no marca match si el fragmento no aparece en ninguna cita", () => {
    expect(isPartOfCitation("garantía", ["El objeto de la licitación es..."])).toBe(false);
  });
});

describe("createCitationTextRenderer", () => {
  test("envuelve en <mark> el texto que coincide con una cita", () => {
    const renderer = createCitationTextRenderer(["El objeto de la licitación es la compra de insumos"]);
    expect(renderer({ str: "objeto" } as never)).toContain("<mark");
    expect(renderer({ str: "objeto" } as never)).toContain("objeto");
  });

  test("deja el texto sin marcar si no coincide con ninguna cita", () => {
    const renderer = createCitationTextRenderer(["El objeto de la licitación es la compra de insumos"]);
    expect(renderer({ str: "garantía" } as never)).not.toContain("<mark");
  });

  test("sin citas, nunca marca nada", () => {
    const renderer = createCitationTextRenderer([]);
    expect(renderer({ str: "objeto" } as never)).not.toContain("<mark");
  });

  test("escapa caracteres HTML del texto original", () => {
    const renderer = createCitationTextRenderer(["a < b & c > d"]);
    expect(renderer({ str: "a < b" } as never)).not.toContain("<b");
    expect(renderer({ str: "a < b" } as never)).toContain("&lt;");
  });
});
