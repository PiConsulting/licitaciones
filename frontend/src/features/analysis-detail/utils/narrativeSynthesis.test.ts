import { buildNarrativeBlocks } from "./narrativeSynthesis";
import type { CategoryData, FieldItem } from "../types";

function createField(
  field_name: string,
  options?: {
    state?: FieldItem["field_state"];
    value?: string | null;
  },
): FieldItem {
  return {
    field_name,
    field_value: options?.value ?? "valor",
    field_state: options?.state ?? "extraido",
    confidence: 0.9,
    citations: [
      {
        text: "Cita de prueba con suficiente longitud como para ser clickeable",
        page: 4,
        document_id: "doc-1",
        document_name: "Pliego.pdf",
      },
    ],
  };
}

function createCategory(items: FieldItem[], summary = "Resumen de prueba"): CategoryData {
  return {
    items,
    confidence: 0.8,
    source_references: [],
    extraction_status: "success",
    summary,
    is_reviewed: false,
  };
}

describe("buildNarrativeBlocks", () => {
  test("devuelve un unico bloque paragraph cuando hay un solo item en una categoria narrativa", () => {
    const category = createCategory([createField("objeto", { value: "Compra de equipamiento" })]);

    const narrative = buildNarrativeBlocks(category, "objeto_alcance");

    expect(narrative.blocks).toHaveLength(1);
    expect(narrative.blocks[0].type).toBe("paragraph");
    expect(narrative.blocks[0]).toMatchObject({ type: "paragraph", text: expect.stringContaining("Compra de equipamiento") });
    expect(narrative.sources).toHaveLength(1);
  });

  test("devuelve un bullet_list cuando hay mas de un item", () => {
    const category = createCategory([
      createField("criterio_1", { value: "Precio" }),
      createField("criterio_2", { value: "Calidad" }),
    ]);

    const narrative = buildNarrativeBlocks(category, "criterios_evaluacion");

    expect(narrative.blocks).toHaveLength(1);
    expect(narrative.blocks[0].type).toBe("bullet_list");
    if (narrative.blocks[0].type === "bullet_list") {
      expect(narrative.blocks[0].items).toHaveLength(2);
    }
  });

  test("fuerza bullet_list para categorias tipo checklist aunque haya un solo item", () => {
    const category = createCategory([createField("anexo", { value: "Anexo I - Formulario de oferta" })]);

    const narrative = buildNarrativeBlocks(category, "anexos_obligatorios");

    expect(narrative.blocks[0].type).toBe("bullet_list");
  });

  test("requisitos_admisibilidad y causales_rechazo con varios hechos van en bullet_list, no apretujados en un parrafo", () => {
    // No hay formato fijo por categoria: varios hechos discretos e
    // independientes se listan, igual que cualquier otra categoria con mas de
    // un item (ver comentario en categoryIcons.tsx sobre por que se saco
    // SINGLE_PARAGRAPH_CATEGORIES).
    const category = createCategory([
      createField("documento", { value: "Certificado fiscal para contratar" }),
      createField("inhabilitacion", { value: "No estar inhabilitado por el Registro de Proveedores" }),
      createField("experiencia_minima", { value: "Acreditar 3 años de experiencia en el rubro" }),
    ]);

    const requisitos = buildNarrativeBlocks(category, "requisitos_admisibilidad");
    expect(requisitos.blocks).toHaveLength(1);
    expect(requisitos.blocks[0].type).toBe("bullet_list");
    if (requisitos.blocks[0].type === "bullet_list") {
      expect(requisitos.blocks[0].items).toHaveLength(3);
      const texts = requisitos.blocks[0].items.map((item) => item.text);
      expect(texts.some((text) => text.includes("Certificado fiscal para contratar"))).toBe(true);
      expect(texts.some((text) => text.includes("No estar inhabilitado por el Registro de Proveedores"))).toBe(true);
      expect(texts.some((text) => text.includes("Acreditar 3 años de experiencia en el rubro"))).toBe(true);
    }

    const causalesCategory = createCategory([
      createField("causal_rechazo", { value: "No presentar la garantía de mantenimiento de oferta" }),
      createField("causal_rechazo", { value: "Presentar la oferta fuera del término fijado" }),
    ]);
    const causales = buildNarrativeBlocks(causalesCategory, "causales_rechazo");
    expect(causales.blocks).toHaveLength(1);
    expect(causales.blocks[0].type).toBe("bullet_list");
  });

  test("requisitos_admisibilidad con un unico hecho va en parrafo, no en lista de un solo item", () => {
    const category = createCategory([createField("documento", { value: "Certificado fiscal para contratar" })]);

    const requisitos = buildNarrativeBlocks(category, "requisitos_admisibilidad");
    expect(requisitos.blocks).toHaveLength(1);
    expect(requisitos.blocks[0].type).toBe("paragraph");
  });

  test("nunca produce un bloque de tipo table", () => {
    const category = createCategory([
      createField("garantia_1", { value: "1%" }),
      createField("garantia_2", { value: "7%" }),
    ]);

    const narrative = buildNarrativeBlocks(category, "garantias");

    expect(narrative.blocks.every((block) => block.type !== "table")).toBe(true);
  });

  test("deduplica fuentes repetidas entre items", () => {
    const sharedCitation = {
      text: "Cita compartida entre dos items del pliego",
      page: 9,
      document_id: "doc-1",
      document_name: "Pliego.pdf",
    };
    const category = createCategory([
      { ...createField("campo_a", { value: "A" }), citations: [sharedCitation] },
      { ...createField("campo_b", { value: "B" }), citations: [sharedCitation] },
    ]);

    const narrative = buildNarrativeBlocks(category, "criterios_evaluacion");

    expect(narrative.sources).toHaveLength(1);
  });

  test("devuelve fallback cuando no hay datos utiles", () => {
    const category = createCategory(
      [createField("garantia_anticipo", { state: "no_encontrado", value: null })],
      "Sin datos extraídos todavía.",
    );

    const narrative = buildNarrativeBlocks(category, "garantias");

    expect(narrative.blocks).toHaveLength(1);
    expect(narrative.blocks[0]).toMatchObject({ type: "paragraph", confidence_level: "low" });
    expect(narrative.sources).toHaveLength(0);
  });

  // FIX (2026-08-13): un item "no_aplica" trae obligatoriamente una `valor`
  // explicando el motivo (ver backend/analysis/extraction/prompts/garantias.txt,
  // Caso 4) -- antes este fallback la descartaba y mostraba siempre la misma
  // frase genérica ("Garantías no aplica para este pliego."), sin importar la
  // explicación real que vino con cita desde el pliego.
  test("item no_aplica con explicacion muestra la explicacion, no una frase generica", () => {
    const category = createCategory([
      createField("mantenimiento_oferta", {
        state: "no_aplica",
        value: "El pliego sólo prevé garantía técnica del equipamiento, ninguna financiera",
      }),
    ]);

    const narrative = buildNarrativeBlocks(category, "garantias");

    expect(narrative.blocks).toHaveLength(1);
    expect(narrative.blocks[0]).toMatchObject({
      type: "paragraph",
      text: expect.stringContaining(
        "El pliego sólo prevé garantía técnica del equipamiento, ninguna financiera",
      ),
    });
    // La cita que respalda la explicación no_aplica se preserva como fuente.
    expect(narrative.sources).toHaveLength(1);
  });

  test("item no_aplica sin explicacion (valor vacio) no cuenta como dato util y cae al fallback", () => {
    // Sin `valor`, un item no_aplica no aporta nada verificable -- distinto
    // del caso con explicación, que sí debe mostrarse (test anterior).
    const category = createCategory([
      createField("mantenimiento_oferta", { state: "no_aplica", value: "" }),
    ]);

    const narrative = buildNarrativeBlocks(category, "garantias");

    expect(narrative.blocks[0]).toMatchObject({
      type: "paragraph",
      text: expect.stringContaining("No se encontró información sobre"),
    });
  });

  test("categoria compuesta solo por items no_aplica no cae al fallback 'no se encontro informacion'", () => {
    // Antes, al no contar como "dato util", una categoria entera de items
    // no_aplica caia en fallbackBlock ("No se encontró información sobre
    // garantías..."), contradiciendo el badge "no aplica" que sí se muestra.
    const category = createCategory([
      createField("mantenimiento_oferta", {
        state: "no_aplica",
        value: "No se exige garantía; el pliego sólo regula su ajuste en caso de corresponder",
      }),
    ]);

    const narrative = buildNarrativeBlocks(category, "garantias");

    expect(narrative.blocks[0]).toMatchObject({
      type: "paragraph",
      text: expect.stringContaining("No se exige garantía"),
    });
  });
});
