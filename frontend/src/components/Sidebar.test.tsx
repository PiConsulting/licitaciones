import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { Sidebar } from "./Sidebar";

describe("Sidebar", () => {
  test("renderiza items de navegación", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Analizar nuevo pliego")).toBeInTheDocument();
  });

  test("marca item activo", () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Sidebar />
      </MemoryRouter>,
    );

    const dashboardItem = screen.getByRole("link", { name: /dashboard/i });
    expect(dashboardItem).toHaveClass("bg-primary-light");
    expect(dashboardItem).toHaveAttribute("aria-current", "page");
  });

  test("toggle collapse/expand", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );

    const aside = screen.getByLabelText("Barra lateral");
    const toggle = screen.getByRole("button", { name: /colapsar menú/i });

    expect(aside).toHaveClass("w-60");
    fireEvent.click(toggle);
    expect(aside).toHaveClass("w-16");
  });
});
