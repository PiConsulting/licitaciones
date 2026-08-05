import { render, screen } from "@testing-library/react";

import { AnalysisProgress } from "./AnalysisProgress";

vi.mock("./CancelButton", () => ({
  CancelButton: () => <div>cancel-button</div>,
}));

describe("AnalysisProgress", () => {
  test("muestra error cuando status es error", () => {
    render(
      <AnalysisProgress
        analysisId="analysis-1"
        status={{
          id: "analysis-1",
          status: "error",
          current_stage: "completed",
          progress_percentage: 90,
          error_message: "El analisis supero el tiempo maximo",
        }}
      />,
    );

    expect(screen.getByText(/supero el tiempo maximo/i)).toBeInTheDocument();
  });

  test("muestra estado cancelado", () => {
    render(
      <AnalysisProgress
        analysisId="analysis-2"
        status={{
          id: "analysis-2",
          status: "cancelled",
          current_stage: "completed",
          progress_percentage: 45,
        }}
      />,
    );

    expect(screen.getByText(/fue cancelado/i)).toBeInTheDocument();
  });
});
