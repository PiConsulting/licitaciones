import { render, screen, fireEvent } from "@testing-library/react";
import { describe, test, expect, vi } from "vitest";
import { SourceReference } from "./SourceReference";

describe("SourceReference", () => {
  test("displays page number", () => {
    render(
      <SourceReference
        documentId="doc-123"
        pageNumber={5}
      />
    );

    expect(screen.getByText("Página 5")).toBeInTheDocument();
  });

  test("displays fragment when provided", () => {
    render(
      <SourceReference
        documentId="doc-123"
        pageNumber={10}
        fragment="El plazo de presentación es de 30 días corridos"
      />
    );

    expect(screen.getByText(/El plazo de presentación es de 30 días corridos/)).toBeInTheDocument();
  });

  test("does not display fragment section when not provided", () => {
    const { container } = render(
      <SourceReference
        documentId="doc-123"
        pageNumber={5}
      />
    );

    const italicText = container.querySelector("p.italic");
    expect(italicText).not.toBeInTheDocument();
  });

  test("displays view button when onView callback is provided", () => {
    const handleView = vi.fn();
    render(
      <SourceReference
        documentId="doc-123"
        pageNumber={5}
        onView={handleView}
      />
    );

    const viewButton = screen.getByLabelText(/ver fuente en el pliego/i);
    expect(viewButton).toBeInTheDocument();
  });

  test("does not display view button when onView is not provided", () => {
    render(
      <SourceReference
        documentId="doc-123"
        pageNumber={5}
      />
    );

    const viewButton = screen.queryByLabelText(/ver fuente en el pliego/i);
    expect(viewButton).not.toBeInTheDocument();
  });

  test("calls onView when view button is clicked", () => {
    const handleView = vi.fn();
    render(
      <SourceReference
        documentId="doc-123"
        pageNumber={5}
        onView={handleView}
      />
    );

    const viewButton = screen.getByLabelText(/ver fuente en el pliego/i);
    fireEvent.click(viewButton);

    expect(handleView).toHaveBeenCalledTimes(1);
  });

  test("view button has correct aria-label with page number", () => {
    const handleView = vi.fn();
    render(
      <SourceReference
        documentId="doc-123"
        pageNumber={42}
        onView={handleView}
      />
    );

    const viewButton = screen.getByLabelText("Ver fuente en el pliego (pág. 42)");
    expect(viewButton).toBeInTheDocument();
  });

  test("displays section heading", () => {
    render(
      <SourceReference
        documentId="doc-123"
        pageNumber={5}
      />
    );

    expect(screen.getByText("Fuente en el documento")).toBeInTheDocument();
  });

  test("has data-testid on view button for easy testing", () => {
    const handleView = vi.fn();
    render(
      <SourceReference
        documentId="doc-123"
        pageNumber={5}
        onView={handleView}
      />
    );

    const viewButton = screen.getByTestId("source-reference-view-button");
    expect(viewButton).toBeInTheDocument();
  });
});
