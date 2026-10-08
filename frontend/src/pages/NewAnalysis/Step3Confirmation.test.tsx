import { fireEvent, render, screen } from "@testing-library/react";

import { saveSession } from "../../auth/session";
import { BUSINESS_UNITS, DEFAULT_BUSINESS_UNIT } from "../../config/businessUnits";
import { DEFAULT_USER_ROLE, SUPERADMIN_ROLE } from "../../config/userRoles";
import type { UploadedFile } from "../../types/upload";
import { Step3Confirmation } from "./Step3Confirmation";

vi.mock("../../hooks/useDocumentUpload", () => ({
  useDocumentUpload: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}));

function buildUploadedFile(name: string): UploadedFile {
  const file = new File(["x"], name, { type: "application/pdf" });
  return {
    id: `${name}-id`,
    file,
    sizeMb: "1.00",
    pagesLabel: "N/D páginas",
    status: "valid",
  };
}

describe("Step3Confirmation", () => {
  const baseFiles = [
    buildUploadedFile("anexo-a.pdf"),
    buildUploadedFile("pliego.pdf"),
    buildUploadedFile("anexo-b.pdf"),
  ];

  test("renderiza primero el archivo designado como principal", () => {
    render(
      <Step3Confirmation
        files={baseFiles}
        primaryIndex={1}
        onBack={() => undefined}
        onContinueToStart={() => undefined}
      />,
    );

    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("pliego.pdf");
    expect(items[0]).toHaveTextContent("Principal");
    expect(items[1]).toHaveTextContent("anexo-a.pdf");
    expect(items[1]).toHaveTextContent("Anexo");
    expect(items[2]).toHaveTextContent("anexo-b.pdf");
    expect(items[2]).toHaveTextContent("Anexo");
  });

  test("muestra campo de nombre de analisis", () => {
    render(
      <Step3Confirmation
        files={baseFiles}
        primaryIndex={1}
        onBack={() => undefined}
        onContinueToStart={() => undefined}
      />,
    );

    expect(screen.getByLabelText(/nombre del análisis/i)).toBeInTheDocument();
  });

  describe("superadmin", () => {
    beforeEach(() => {
      localStorage.clear();
      saveSession({ email: "admin@cedia.com", role: SUPERADMIN_ROLE, business_unit: DEFAULT_BUSINESS_UNIT });
    });

    test("muestra todas las unidades del catálogo", () => {
      render(
        <Step3Confirmation
          files={baseFiles}
          primaryIndex={1}
          onBack={() => undefined}
          onContinueToStart={() => undefined}
        />,
      );

      BUSINESS_UNITS.forEach((unit) => {
        expect(screen.getByRole("button", { name: unit })).toBeInTheDocument();
      });
    });

    test("envía la unidad elegida", () => {
      const onContinue = vi.fn();
      const chosenUnit = BUSINESS_UNITS[BUSINESS_UNITS.length - 1];
      render(
        <Step3Confirmation
          files={baseFiles}
          primaryIndex={1}
          onBack={() => undefined}
          onContinueToStart={onContinue}
        />,
      );

      fireEvent.click(screen.getByRole("button", { name: chosenUnit }));
      fireEvent.click(screen.getByRole("button", { name: /iniciar análisis/i }));

      expect(onContinue).toHaveBeenCalledWith({ analysisName: "", businessUnit: chosenUnit });
    });
  });

  describe("miembro", () => {
    beforeEach(() => {
      localStorage.clear();
      saveSession({ email: "miembro@cedia.com", role: DEFAULT_USER_ROLE, business_unit: BUSINESS_UNITS[1] });
    });

    test("no muestra el selector de unidad", () => {
      render(
        <Step3Confirmation
          files={baseFiles}
          primaryIndex={1}
          onBack={() => undefined}
          onContinueToStart={() => undefined}
        />,
      );

      expect(screen.queryByText(/unidad de negocio/i)).not.toBeInTheDocument();
      BUSINESS_UNITS.forEach((unit) => {
        expect(screen.queryByRole("button", { name: unit })).not.toBeInTheDocument();
      });
    });

    test("continúa con la unidad asignada al usuario", () => {
      const onContinue = vi.fn();
      render(
        <Step3Confirmation
          files={baseFiles}
          primaryIndex={1}
          onBack={() => undefined}
          onContinueToStart={onContinue}
        />,
      );

      fireEvent.click(screen.getByRole("button", { name: /iniciar análisis/i }));

      expect(onContinue).toHaveBeenCalledWith({ analysisName: "", businessUnit: BUSINESS_UNITS[1] });
    });
  });
});
