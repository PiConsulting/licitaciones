import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { Sidebar } from "./Sidebar";

describe("Sidebar", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  test("renderiza items de navegación", () => {
    localStorage.setItem("user_name", "Agostina Torres");

    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(screen.getByText("Analizar nuevo pliego")).toBeInTheDocument();
    expect(screen.getByText("Historial")).toBeInTheDocument();
    expect(screen.getByText("Dashboard (próximamente)")).toBeInTheDocument();
    expect(screen.getByText("Agostina Torres")).toBeInTheDocument();
  });

  test("marca item activo", () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Sidebar />
      </MemoryRouter>,
    );

    const historialItem = screen.getByRole("link", { name: /historial/i });
    expect(historialItem).toHaveClass("bg-primary-light");
    expect(historialItem).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("link", { name: /^dashboard$/i })).not.toBeInTheDocument();
  });

  test("toggle collapse/expand", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    const aside = screen.getByLabelText("Barra lateral");
    const toggle = screen.getByRole("button", { name: /colapsar menú/i });

    expect(aside).toHaveClass("w-52");
    fireEvent.click(toggle);
    expect(aside).toHaveClass("w-16");
  });
});
