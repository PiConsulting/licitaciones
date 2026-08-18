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
    // La navegación anterior/siguiente del visor no puede pasearse por las
    // citas de los otros bullets: se verifica ESTA afirmación.
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
});

describe("categorías de párrafo: se conserva el listado", () => {
  test("un párrafo mantiene Fuentes verificables al pie", () => {
    render(<NarrativeBlocks narrative={PARRAFO} />);

    expect(screen.getByTestId("category-sources")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Pliego\.pdf · pág\. 1/i })).toBeInTheDocument();
  });

  test("el párrafo no lleva ojo: la lectura corrida no se interrumpe", () => {
    render(<NarrativeBlocks narrative={PARRAFO} />);

    expect(screen.queryByTestId("item-source-button")).not.toBeInTheDocument();
  });

  test("si hay párrafos y bullets, el listado sólo trae las fuentes de los párrafos", () => {
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

    const listado = screen.getByTestId("category-sources-list");
    expect(within(listado).getAllByRole("button")).toHaveLength(1);
    expect(within(listado).getByRole("button", { name: /pág\. 1/i })).toBeInTheDocument();
    // La fuente del bullet vive en su ojo, no acá.
    expect(within(listado).queryByRole("button", { name: /pág\. 5/i })).not.toBeInTheDocument();
    expect(screen.getAllByTestId("item-source-button")).toHaveLength(1);
  });
});
