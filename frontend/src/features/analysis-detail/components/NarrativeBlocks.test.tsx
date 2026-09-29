/**
 * La evidencia se ofrece según la forma del contenido.
 *
 * Antes, TODA la evidencia de una categoría iba a un listado "Fuentes
 * verificables" al pie, con una entrada por fuente rotulada
 * "Pliego.pdf · pág. 4". Para una categoría como Requisitos de Admisibilidad,
 * que son ocho bullets, eso obliga a la persona a cruzar una lista de ocho
 * afirmaciones contra una lista de ocho fuentes indistinguibles entre sí para
 * verificar una sola.
 *
 * Ahora cada bullet y cada fila de tabla lleva su propio botón -- un ojo
 * discreto -- que abre el PDF en SU cita. Los párrafos, que no tienen un ítem
 * discreto donde anclar el botón, mantienen el listado (es el caso de Objeto y
 * Alcance).
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { NarrativeBlocks } from "./NarrativeBlocks";
import type { CategoryNarrative, NarrativeSource } from "../types";

function source(id: number, page: number, text: string): NarrativeSource {
  return {
    id,
    document_id: "doc-1",
    document_name: "Pliego.pdf",
    page,
    text,
  };
}

const BULLETS: CategoryNarrative = {
  blocks: [
    {
      type: "bullet_list",
      items: [
        { text: "Presentar constancia RUP vigente.", confidence_level: "high", source_ids: [0] },
        { text: "Acreditar antecedentes de los últimos 3 años.", confidence_level: "high", source_ids: [1] },
      ],
    },
  ],
  sources: [
    source(0, 4, "constancia de inscripción en el Registro Único de Proveedores vigente"),
    source(1, 7, "antecedentes de provisión de los últimos tres (3) años"),
  ],
};

const PARRAFO: CategoryNarrative = {
  blocks: [
    {
      type: "paragraph",
      text: "Se licita el servicio de limpieza integral de los edificios municipales.",
      confidence_level: "high",
      source_ids: [0],
    },
  ],
  sources: [source(0, 1, "servicio de limpieza integral de los edificios municipales")],
};

describe("categorías de ítems: un ojo por ítem", () => {
  test("cada bullet lleva su propio botón de fuente", () => {
    render(<NarrativeBlocks narrative={BULLETS} />);

    expect(screen.getAllByTestId("item-source-button")).toHaveLength(2);
  });

  test("el ojo de un bullet abre SOLO la cita de ese bullet", async () => {
    const user = userEvent.setup();
    const onViewSource = vi.fn();
    render(<NarrativeBlocks narrative={BULLETS} onViewSource={onViewSource} />);

    const segundo = screen.getAllByTestId("item-source-button")[1];
    await user.click(segundo);

    expect(onViewSource).toHaveBeenCalledTimes(1);
    const payload = onViewSource.mock.calls[0][0];
    expect(payload.citation.page).toBe(7);
    // La navegación anterior/siguiente del visor no puede pasearse por las citas de los otros bullets.
    expect(payload.citations).toHaveLength(1);
    expect(payload.sources).toHaveLength(1);
  });

  test("el ojo dice a qué página lleva, para lectores de pantalla", () => {
    render(<NarrativeBlocks narrative={BULLETS} />);

    expect(screen.getByRole("button", { name: /pág\. 4/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pág\. 7/i })).toBeInTheDocument();
  });

  test("una categoría de bullets ya no muestra el listado de fuentes al pie", () => {
    render(<NarrativeBlocks narrative={BULLETS} />);

    expect(screen.queryByTestId("category-sources")).not.toBeInTheDocument();
    expect(screen.queryByText(/Fuentes verificables/i)).not.toBeInTheDocument();
  });

  test("no queda ningún punto de bullet visual -- todo ítem se renderiza como título + detalle", () => {
    const { container } = render(<NarrativeBlocks narrative={BULLETS} />);

    expect(container.querySelector(".rounded-full.bg-\\[rgba\\(0\\,60\\,107\\,\\.35\\)\\]")).not.toBeInTheDocument();
  });

  test("con `titulo` real, se muestra arriba (junto al ojo) y el texto completo queda como detalle debajo", () => {
    const narrative: CategoryNarrative = {
      blocks: [
        {
          type: "bullet_list",
          items: [
            {
              text: "Acreditar al menos tres proyectos similares en los últimos cinco años, con referencias de clientes.",
              titulo: "Antecedentes: 3 contratos similares en 5 años",
              confidence_level: "high",
              source_ids: [0],
            },
          ],
        },
      ],
      sources: [source(0, 15, "contratos de provisión e instalación de networking")],
    };

    render(<NarrativeBlocks narrative={narrative} />);

    expect(screen.getByText("Antecedentes: 3 contratos similares en 5 años")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Acreditar al menos tres proyectos similares en los últimos cinco años, con referencias de clientes.",
      ),
    ).toBeInTheDocument();
  });

  test("sin `titulo` pero con ':' en el texto (narrativa vieja), separa en título + detalle igual", () => {
    const narrative: CategoryNarrative = {
      blocks: [
        {
          type: "bullet_list",
          items: [
            { text: "Documento: Garantía de la oferta.", confidence_level: "high", source_ids: [0] },
          ],
        },
      ],
      sources: [source(0, 3, "garantía de la oferta")],
    };

    render(<NarrativeBlocks narrative={narrative} />);

    expect(screen.getByText("Documento")).toBeInTheDocument();
    expect(screen.getByText("Garantía de la oferta.")).toBeInTheDocument();
  });

  test("un bullet sin fuente verificable no muestra un ojo que no lleva a ningún lado", () => {
    const narrative: CategoryNarrative = {
      blocks: [
        {
          type: "bullet_list",
          items: [
            { text: "Con fuente.", confidence_level: "high", source_ids: [0] },
            { text: "Sin fuente.", confidence_level: "low", source_ids: [] },
          ],
        },
      ],
      sources: [source(0, 4, "texto respaldado")],
    };

    render(<NarrativeBlocks narrative={narrative} />);

    expect(screen.getAllByTestId("narrative-bullet-item")).toHaveLength(2);
    expect(screen.getAllByTestId("item-source-button")).toHaveLength(1);
  });

  test("una fuente marcada como no verificada por el backend no habilita el ojo", () => {
    const narrative: CategoryNarrative = {
      blocks: [
        {
          type: "bullet_list",
          items: [{ text: "Afirmación sin respaldo real.", confidence_level: "low", source_ids: [0] }],
        },
      ],
      sources: [{ ...source(0, 4, "cita que no se pudo respaldar"), unverified: true }],
    };

    render(<NarrativeBlocks narrative={narrative} />);

    expect(screen.queryByTestId("item-source-button")).not.toBeInTheDocument();
    expect(screen.getByTestId("category-sources-empty")).toBeInTheDocument();
  });

  test("las filas de tabla también llevan su ojo", () => {
    const narrative: CategoryNarrative = {
      blocks: [
        {
          type: "table",
          headers: ["Factor", "Puntaje"],
          rows: [
            { cells: ["Precio", "60"], confidence_level: "high", source_ids: [0] },
            { cells: ["Técnica", "40"], confidence_level: "high", source_ids: [1] },
          ],
        },
      ],
      sources: [source(0, 9, "precio: sesenta (60) puntos"), source(1, 9, "propuesta técnica: cuarenta (40) puntos")],
    };

    render(<NarrativeBlocks narrative={narrative} />);

    expect(within(screen.getByTestId("narrative-table")).getAllByTestId("item-source-button")).toHaveLength(2);
  });

  test("mantiene bullets en una única lista continua aunque vengan de varios documentos", () => {
    const narrative: CategoryNarrative = {
      blocks: [
        {
          type: "bullet_list",
          items: [
            { text: "Req pliego", confidence_level: "high", source_ids: [0] },
            { text: "Req anexo A", confidence_level: "high", source_ids: [1] },
            { text: "Req anexo B", confidence_level: "high", source_ids: [2] },
          ],
        },
      ],
      sources: [
        { ...source(0, 1, "req pliego"), document_id: "doc-p", document_name: "Pliego Principal.pdf" },
        { ...source(1, 2, "req anexo a"), document_id: "doc-a", document_name: "Anexo A.pdf" },
        { ...source(2, 3, "req anexo b"), document_id: "doc-b", document_name: "Anexo B.pdf" },
      ],
    };

    render(<NarrativeBlocks narrative={narrative} />);

    expect(screen.getAllByTestId("narrative-bullet-item")).toHaveLength(3);
    expect(screen.queryByTestId("document-source-divider")).not.toBeInTheDocument();
    expect(screen.queryByTestId("document-source-group-label")).not.toBeInTheDocument();
  });

  test("en bullets no muestra divisores ni labels de documento", () => {
    render(<NarrativeBlocks narrative={BULLETS} />);

    expect(screen.queryByTestId("document-source-divider")).not.toBeInTheDocument();
    expect(screen.queryByTestId("document-source-group-label")).not.toBeInTheDocument();
  });

  test("con un porcentaje en el detalle (ej. garantías), lo muestra en negrita junto al título", () => {
    const narrative: CategoryNarrative = {
      blocks: [
        {
          type: "bullet_list",
          items: [
            {
              titulo: "Garantía de mantenimiento de oferta",
              text: "Debe ser del 4% del valor total de la oferta y acompañarse con la propuesta.",
              confidence_level: "high",
              source_ids: [0],
            },
          ],
        },
      ],
      sources: [source(0, 5, "cuatro por ciento del valor total de la oferta")],
    };

    render(<NarrativeBlocks narrative={narrative} />);

    const highlight = screen.getByTestId("narrative-bullet-highlight");
    expect(highlight).toHaveTextContent("4%");
    expect(highlight.tagName).toBe("SPAN");
    expect(highlight.className).toMatch(/font-bold/);
  });

  test("sin porcentaje, cae al monto en pesos ($ ...) como highlight", () => {
    const narrative: CategoryNarrative = {
      blocks: [
        {
          type: "bullet_list",
          items: [
            {
              titulo: "Garantía de mantenimiento de oferta",
              text: "No resulta necesario presentarla cuando el monto de la oferta no supere $ 40.000.000.",
              confidence_level: "high",
              source_ids: [0],
            },
          ],
        },
      ],
      sources: [source(0, 5, "no supere $ 40.000.000")],
    };

    render(<NarrativeBlocks narrative={narrative} />);

    expect(screen.getByTestId("narrative-bullet-highlight")).toHaveTextContent("$40.000.000");
  });

  test("sin porcentaje ni monto (ej. garantía técnica), no muestra ningún highlight", () => {
    const narrative: CategoryNarrative = {
      blocks: [
        {
          type: "bullet_list",
          items: [
            {
              titulo: "Garantía técnica del equipamiento",
              text: "El pliego prevé una garantía técnica de 36 meses, contados desde la Recepción Provisional.",
              confidence_level: "high",
              source_ids: [0],
            },
          ],
        },
      ],
      sources: [source(0, 6, "garantía técnica de 36 meses")],
    };

    render(<NarrativeBlocks narrative={narrative} />);

    expect(screen.queryByTestId("narrative-bullet-highlight")).not.toBeInTheDocument();
  });
});

describe("categorías de párrafo: se conserva el listado", () => {
  test("un párrafo mantiene Fuentes verificables al pie en modo colapsado", async () => {
    const user = userEvent.setup();
    render(<NarrativeBlocks narrative={PARRAFO} />);

    expect(screen.getByTestId("category-sources")).toBeInTheDocument();
    expect(screen.queryByTestId("category-sources-list")).not.toBeInTheDocument();

    await user.click(screen.getByTestId("paragraph-sources-toggle"));

    expect(screen.getByRole("button", { name: /Pliego\.pdf · pág\. 1/i })).toBeInTheDocument();
  });

  test("el párrafo no lleva ojo: la lectura corrida no se interrumpe", () => {
    render(<NarrativeBlocks narrative={PARRAFO} />);

    expect(screen.queryByTestId("item-source-button")).not.toBeInTheDocument();
  });

  test("si hay párrafos y bullets, el listado sólo trae las fuentes de los párrafos", async () => {
    const user = userEvent.setup();
    const mixto: CategoryNarrative = {
      blocks: [
        { type: "paragraph", text: "Contexto general.", confidence_level: "high", source_ids: [0] },
        {
          type: "bullet_list",
          items: [{ text: "Un requisito puntual.", confidence_level: "high", source_ids: [1] }],
        },
      ],
      sources: [source(0, 1, "texto del contexto general"), source(1, 5, "texto del requisito puntual")],
    };

    render(<NarrativeBlocks narrative={mixto} />);
    await user.click(screen.getByTestId("paragraph-sources-toggle"));

    const listado = screen.getByTestId("category-sources-list");
    expect(within(listado).getAllByRole("button")).toHaveLength(1);
    expect(within(listado).getByRole("button", { name: /pág\. 1/i })).toBeInTheDocument();
    // La fuente del bullet vive en su ojo, no acá.
    expect(within(listado).queryByRole("button", { name: /pág\. 5/i })).not.toBeInTheDocument();
    expect(screen.getAllByTestId("item-source-button")).toHaveLength(1);
  });

  test("si hay múltiples fuentes de párrafo se muestran juntas sin divisor", async () => {
    const user = userEvent.setup();
    const narrative: CategoryNarrative = {
      blocks: [
        {
          type: "paragraph",
          text: "Resumen.",
          confidence_level: "high",
          source_ids: [0, 1, 2],
        },
      ],
      sources: [
        {
          id: 0,
          document_id: "doc-a",
          document_name: "Anexo B.pdf",
          page: 3,
          text: "texto b",
        },
        {
          id: 1,
          document_id: "doc-p",
          document_name: "Pliego Principal.pdf",
          page: 1,
          text: "texto pliego",
        },
        {
          id: 2,
          document_id: "doc-c",
          document_name: "Anexo A.pdf",
          page: 2,
          text: "texto a",
        },
      ],
    };

    render(<NarrativeBlocks narrative={narrative} />);
    await user.click(screen.getByTestId("paragraph-sources-toggle"));

    expect(screen.queryByTestId("document-source-divider")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Pliego Principal\.pdf · pág\. 1/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Anexo A\.pdf · pág\. 2/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Anexo B\.pdf · pág\. 3/i })).toBeInTheDocument();
  });

});
