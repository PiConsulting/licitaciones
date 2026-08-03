import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AppLayout } from "./AppLayout";

describe("AppLayout", () => {
  test("renderiza children en main", () => {
    render(
      <MemoryRouter>
        <AppLayout>
          <div>Test Content</div>
        </AppLayout>
      </MemoryRouter>,
    );

    expect(screen.getByRole("main")).toContainElement(screen.getByText("Test Content"));
  });

  test("skip link funcional", () => {
    render(
      <MemoryRouter>
        <AppLayout>
          <div>Contenido</div>
        </AppLayout>
      </MemoryRouter>,
    );

    const skipLink = screen.getByText("Saltar al contenido principal");
    expect(skipLink).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });
});
