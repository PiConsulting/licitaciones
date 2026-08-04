import { render, screen } from "@testing-library/react";

import { TimeoutWarning } from "./TimeoutWarning";

describe("TimeoutWarning", () => {
  test("muestra warning cuando corresponde", () => {
    render(<TimeoutWarning show={true} />);
    expect(screen.getByText(/demorando mas de lo esperado/i)).toBeInTheDocument();
  });

  test("no renderiza cuando no corresponde", () => {
    const { container } = render(<TimeoutWarning show={false} />);
    expect(container.firstChild).toBeNull();
  });
});
