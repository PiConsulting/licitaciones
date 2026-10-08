import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { AppLayout } from "./AppLayout";

function renderWithProviders(ui: ReactElement, initialEntries: string[] = ["/"]) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Accessibility", () => {
  test("skip link visible en focus", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <AppLayout>
        <button>Main Button</button>
      </AppLayout>,
    );

    const skipLink = screen.getByText("Saltar al contenido principal");
    expect(skipLink).toHaveClass("sr-only");

    await user.tab();
    expect(skipLink).toHaveFocus();
    expect(skipLink.className).toContain("focus:not-sr-only");
  });

  test("tab order lógico inicia en skip link", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <AppLayout>
        <button>Main Button</button>
      </AppLayout>,
      ["/dashboard"],
    );

    await user.tab();
    expect(screen.getByText("Saltar al contenido principal")).toHaveFocus();
  });
});
