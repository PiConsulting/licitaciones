import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { AppLayout } from "./AppLayout";

describe("Accessibility", () => {
  test("skip link visible en focus", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <AppLayout>
          <button>Main Button</button>
        </AppLayout>
      </MemoryRouter>,
    );

    const skipLink = screen.getByText("Saltar al contenido principal");
    expect(skipLink).toHaveClass("sr-only");

    await user.tab();
    expect(skipLink).toHaveFocus();
    expect(skipLink.className).toContain("focus:not-sr-only");
  });

  test("tab order lógico inicia en skip link", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <AppLayout>
          <button>Main Button</button>
        </AppLayout>
      </MemoryRouter>,
    );

    await user.tab();
    expect(screen.getByText("Saltar al contenido principal")).toHaveFocus();
  });
});
