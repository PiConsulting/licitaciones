import { render, screen } from "@testing-library/react";

import { ProgressBar } from "./ProgressBar";

describe("ProgressBar", () => {
  test("muestra etapa y porcentaje", () => {
    render(<ProgressBar stage="analyzing" progress={45} isProcessing={true} stageProgress="Analizando categorias (4 de 8)" />);

    expect(screen.getByText("Analizando categorias")).toBeInTheDocument();
    expect(screen.getByText("45%")).toBeInTheDocument();
  });

  test("muestra spinner solo en procesamiento", () => {
    const { container, rerender } = render(<ProgressBar stage="analyzing" progress={45} isProcessing={true} />);
    expect(container.querySelector(".animate-spin")).toBeInTheDocument();

    rerender(<ProgressBar stage="completed" progress={100} isProcessing={false} />);
    expect(container.querySelector(".animate-spin")).toBeNull();
  });
});
