import { render, screen } from "@testing-library/react";

import { Button } from "./Button";

describe("Button", () => {
  test("renderiza variantes CEDI", () => {
    const { rerender } = render(<Button variant="primary">Primary</Button>);
    expect(screen.getByRole("button")).toHaveClass("bg-cedi-gradient-button", "text-cedi-white");

    rerender(<Button variant="secondary">Secondary</Button>);
    expect(screen.getByRole("button")).toHaveClass("bg-cedi-white", "text-cedi-navy");

    rerender(<Button variant="danger">Danger</Button>);
    expect(screen.getByRole("button")).toHaveClass("bg-error", "text-white");

    rerender(<Button variant="ghost">Ghost</Button>);
    expect(screen.getByRole("button")).toHaveClass("bg-transparent", "text-cedi-celeste");
  });

  test("renderiza tamaños con alturas del DS", () => {
    const { rerender } = render(<Button size="sm">Small</Button>);
    expect(screen.getByRole("button")).toHaveClass("h-8");

    rerender(<Button size="md">Medium</Button>);
    expect(screen.getByRole("button")).toHaveClass("h-10");

    rerender(<Button size="lg">Large</Button>);
    expect(screen.getByRole("button")).toHaveClass("h-11");
  });

  test("usa forma pill en todas las variantes", () => {
    render(<Button>Label</Button>);
    expect(screen.getByRole("button")).toHaveClass("rounded-full");
  });

  test("estado loading", () => {
    render(<Button loading>Submit</Button>);
    expect(screen.getByTestId("loader-icon")).toBeInTheDocument();
    expect(screen.getByRole("button")).toBeDisabled();
  });

  test("estado disabled", () => {
    render(<Button disabled>Disabled</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
    expect(screen.getByRole("button")).toHaveClass("cursor-not-allowed");
  });
});
