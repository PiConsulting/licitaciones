import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AppLayout } from "./AppLayout";
import { useUIStore } from "../store/useUIStore";

describe("AppLayout", () => {
  beforeEach(() => {
    useUIStore.setState({ sidebarCollapsed: false, theme: "cedia" });
  });

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

  test("permite ocultar y mostrar el sidebar", () => {
    render(
      <MemoryRouter>
        <AppLayout>
          <div>Contenido</div>
        </AppLayout>
      </MemoryRouter>,
    );

    const sidebar = screen.getByLabelText("Barra lateral");
    expect(sidebar).toBeInTheDocument();
    expect(sidebar).toHaveClass("w-[232px]");

    const toggleButton = screen.getByRole("button", { name: /Colapsar barra lateral/i });
    fireEvent.click(toggleButton);

    expect(screen.getByLabelText("Barra lateral")).toHaveClass("w-[72px]");
    expect(screen.getByRole("button", { name: /Expandir barra lateral/i })).toBeInTheDocument();

    const expandButton = screen.getByRole("button", { name: /Expandir barra lateral/i });
    fireEvent.click(expandButton);

    expect(screen.getByLabelText("Barra lateral")).toHaveClass("w-[232px]");
  });
});
