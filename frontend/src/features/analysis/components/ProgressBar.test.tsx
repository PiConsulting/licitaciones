import { act, render, screen } from "@testing-library/react";

import { ProgressBar } from "./ProgressBar";

describe("ProgressBar (fila del Home)", () => {
  test("muestra el progreso real del backend", () => {
    render(<ProgressBar stage="extracting_text" progress={30} />);
    expect(screen.getByText("30%")).toBeInTheDocument();
  });

  test(
    "reinicia a 0% al arrancar una corrida nueva en vez de quedar pegado en el % simulado " +
      "de la corrida anterior (bug real: aprobar fase 2 después de que 'analyzing' ya había " +
      "simulado hasta 75% dejaba el próximo arranque pegado en 75%, porque el ratchet " +
      "Math.max(prev, progress) nunca vuelve a bajar)",
    () => {
      vi.useFakeTimers();
      try {
        const { rerender } = render(<ProgressBar stage="analyzing" progress={10} />);

        act(() => {
          vi.advanceTimersByTime(70_000);
        });
        expect(screen.getByText("75%")).toBeInTheDocument();

        rerender(<ProgressBar stage="queued" progress={0} />);
        expect(screen.getByText("0%")).toBeInTheDocument();
      } finally {
        vi.useRealTimers();
      }
    },
  );
});
