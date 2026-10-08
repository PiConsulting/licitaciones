import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

import { AppLayout } from "./AppLayout";
import { useUIStore } from "../store/useUIStore";

function renderLayout(children: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AppLayout>{children}</AppLayout>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AppLayout", () => {
  beforeEach(() => {
    useUIStore.setState({ sidebarCollapsed: false, theme: "cedia" });
  });

  test("renderiza children en main", () => {
    renderLayout(<div>Test Content</div>);

    expect(screen.getByRole("main")).toContainElement(screen.getByText("Test Content"));
  });

  test("skip link funcional", () => {
    renderLayout(<div>Contenido</div>);

    const skipLink = screen.getByText("Saltar al contenido principal");
    expect(skipLink).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });

  test("permite ocultar y mostrar el sidebar", () => {
    renderLayout(<div>Contenido</div>);

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

  test("en /dashboard muestra el header de Home con el CTA de nuevo pliego", () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/"]}>
          <AppLayout>
            <div>Home</div>
          </AppLayout>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const banner = screen.getAllByRole("banner")[0];
    expect(banner).toHaveTextContent("CedIA");
    expect(banner).toHaveTextContent("Home");
    expect(banner).toHaveTextContent("Analizar nuevo pliego");
  });
});
