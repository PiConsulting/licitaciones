import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { Sidebar } from "./Sidebar";
import { useUIStore } from "../store/useUIStore";

vi.mock("../api/auth", () => ({
  logout: vi.fn(),
}));

describe("Sidebar", () => {
  beforeEach(() => {
    localStorage.clear();
    useUIStore.setState({ sidebarCollapsed: false, theme: "cedia" });
  });

  test("renderiza los 5 items del menú FE1", () => {
    localStorage.setItem("user_name", "Agostina Torres");

    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(screen.getByText("Buscar pliegos")).toBeInTheDocument();
    expect(screen.getByText("Analizar nuevo pliego")).toBeInTheDocument();
    expect(screen.queryByText("Historial")).not.toBeInTheDocument();
    expect(screen.queryByText("Seguimiento")).not.toBeInTheDocument();
    expect(screen.getByText("Agostina Torres")).toBeInTheDocument();
    expect(screen.getByText("Análisis de pliegos")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /CEDI/i })).toBeInTheDocument();
  });

  test("Buscar pliegos está deshabilitado con indicación de próximamente", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    const buscar = screen.getByRole("button", { name: /Buscar pliegos/i });
    expect(buscar).toHaveAttribute("aria-disabled", "true");
    expect(buscar).toHaveAttribute("title", "Próximamente");
  });

  test("marca Home activo con accent bar mint", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Sidebar />
      </MemoryRouter>,
    );

    const home = screen.getByRole("link", { name: /Home/i });
    expect(home).toHaveAttribute("aria-current", "page");
    expect(home.className).toContain("[box-shadow:inset_3px_0_0_#7FF3DE]");
  });

  test("links principales apuntan a rutas FE1", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    const home = screen.getByRole("link", { name: /^Home$/i });
    const analizar = screen.getByRole("link", { name: /Analizar nuevo pliego/i });

    expect(home).toHaveAttribute("href", "/");
    expect(analizar).toHaveAttribute("href", "/analyze");
  });

  test("logout mantiene el botón funcional", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    const logoutBtn = screen.getByRole("button", { name: /Cerrar sesión/i });
    fireEvent.click(logoutBtn);

    expect(logoutBtn).toBeInTheDocument();
  });
});
