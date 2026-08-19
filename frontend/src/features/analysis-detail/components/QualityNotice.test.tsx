/**
 * ATR-03: el usuario tiene que poder distinguir por qué una categoría quedó
 * incompleta.
 *
 * El pipeline ya descartaba correctamente los hallazgos sin cita verificable,
 * pero ese descarte moría en un log del backend. La categoría llegaba marcada
 * "parcial" y no había forma de diferenciar "el pliego dice poco" de "el modelo
 * produjo hallazgos que no pudimos respaldar" -- que es justo la señal de si
 * conviene desconfiar de lo que quedó.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { QualityNotice } from "./QualityNotice";

describe("aviso de calidad de la categoría", () => {
  test("sin descartes no muestra nada", () => {
    render(<QualityNotice quality={{ conservados: 5 }} />);

    expect(screen.queryByTestId("category-quality-notice")).not.toBeInTheDocument();
  });

  test("sin datos de calidad no muestra nada", () => {
    render(<QualityNotice />);

    expect(screen.queryByTestId("category-quality-notice")).not.toBeInTheDocument();
  });

  test("avisa cuántos hallazgos se omitieron", () => {
    render(<QualityNotice quality={{ descartados_sin_evidencia: 3, conservados: 1 }} />);

    expect(screen.getByTestId("category-quality-notice")).toHaveTextContent(
      /3 hallazgos no pudieron respaldarse/i,
    );
  });

  test("usa singular cuando es uno solo", () => {
    render(<QualityNotice quality={{ descartados_sin_evidencia: 1 }} />);

    expect(screen.getByTestId("category-quality-notice")).toHaveTextContent(
      /1 hallazgo no pudo respaldarse/i,
    );
  });

  test("suma los descartes por formato a los de evidencia", () => {
    render(<QualityNotice quality={{ descartados_sin_evidencia: 2, descartados_por_formato: 1 }} />);

    expect(screen.getByTestId("category-quality-notice")).toHaveTextContent(/3 hallazgos/i);
  });

  test("avisa también cuando la cita mostrada no es la que el modelo declaró", () => {
    render(<QualityNotice quality={{ con_evidencia_rescatada: 2, conservados: 4 }} />);

    expect(screen.getByTestId("category-quality-notice")).toHaveTextContent(
      /2 citas no coinciden con lo que el modelo declaró/i,
    );
  });

  test("los dos avisos conviven", () => {
    render(<QualityNotice quality={{ descartados_sin_evidencia: 1, con_evidencia_rescatada: 1 }} />);

    const aviso = screen.getByTestId("category-quality-notice");
    expect(aviso).toHaveTextContent(/no pudo respaldarse/i);
    expect(aviso).toHaveTextContent(/no coincide/i);
  });
});
