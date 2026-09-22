import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { Sidebar } from "./Sidebar";
import { useUIStore } from "../store/useUIStore";

describe("Sidebar", () => {
  beforeEach(() => {
    localStorage.clear();
    // El store de zustand es singleton a nivel módulo; sin reset, el estado se filtra entre tests.
    useUIStore.setState({ sidebarCollapsed: true });
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

  test("está colapsado por default", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    const aside = screen.getByLabelText("Barra lateral");
    expect(aside).toHaveClass("w-16");
    expect(screen.getByRole("button", { name: /expandir menú/i })).toBeInTheDocument();
  });

  test("toggle collapse/expand", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    const aside = screen.getByLabelText("Barra lateral");
    const toggle = screen.getByRole("button", { name: /expandir menú/i });

    expect(aside).toHaveClass("w-16");
    fireEvent.click(toggle);
    expect(aside).toHaveClass("w-52");
  });

  test("se vuelve a colapsar solo al elegir una sección (2026-09-01)", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    const aside = screen.getByLabelText("Barra lateral");
    const expandToggle = screen.getByRole("button", { name: /expandir menú/i });

    fireEvent.click(expandToggle);
    expect(aside).toHaveClass("w-52");

    const historialLink = screen.getByRole("link", { name: /historial/i });
    fireEvent.click(historialLink);

    expect(aside).toHaveClass("w-16");
  });
});
