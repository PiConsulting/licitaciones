import { render, screen } from "@testing-library/react";
import { CheckCircle } from "lucide-react";

import { Badge } from "./Badge";

describe("Badge", () => {
  test("aplica las clases del tono correspondiente", () => {
    render(<Badge tone="success">Ok</Badge>);
    expect(screen.getByText("Ok")).toHaveClass("bg-success-light", "text-success");
  });

  test("critical y highlight usan colores distintos", () => {
    render(
      <>
        <Badge tone="critical">Baja</Badge>
        <Badge tone="highlight">Crítica</Badge>
      </>,
    );
    expect(screen.getByText("Baja")).toHaveClass("bg-critical-light", "text-critical");
    expect(screen.getByText("Crítica")).toHaveClass("bg-highlight-light", "text-highlight");
  });

  test("renderiza el ícono cuando se provee", () => {
    render(
      <Badge tone="success" icon={CheckCircle}>
        Revisada
      </Badge>,
    );
    expect(screen.getByText("Revisada").querySelector("svg")).toBeInTheDocument();
  });
});
