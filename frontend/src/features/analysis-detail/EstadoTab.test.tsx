import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ToastProvider } from "../../components/ToastContainer";
import type { BusinessState, BusinessStatus } from "../../types/businessStatus";
import { EstadoTab } from "./EstadoTab";
import { todayIso } from "./utils/businessStatus";

const mockGetBusinessState = vi.fn();
const mockUpdateBusinessStatus = vi.fn();
const mockSavePresentation = vi.fn();
const mockSaveResult = vi.fn();
const mockUploadReceipt = vi.fn();
const mockDeleteReceipt = vi.fn();
const mockReceiptLink = vi.fn();

vi.mock("../../api/businessStatus", () => ({
  getBusinessState: (...args: unknown[]) => mockGetBusinessState(...args),
  updateBusinessStatus: (...args: unknown[]) => mockUpdateBusinessStatus(...args),
  savePresentation: (...args: unknown[]) => mockSavePresentation(...args),
  saveResult: (...args: unknown[]) => mockSaveResult(...args),
  uploadPresentationReceipt: (...args: unknown[]) => mockUploadReceipt(...args),
  deletePresentationReceipt: (...args: unknown[]) => mockDeleteReceipt(...args),
  getPresentationReceiptLink: (...args: unknown[]) => mockReceiptLink(...args),
}));

function buildState(status: BusinessStatus, overrides: Partial<BusinessState> = {}): BusinessState {
  return {
    id: "analysis-1",
    business_status: status,
    presentation: null,
    result: null,
    history: [
      {
        previous_status: null,
        new_status: "en_analisis",
        changed_by_name: null,
        changed_at: "2026-09-08T10:00:00Z",
        note: null,
      },
      {
        previous_status: "en_analisis",
        new_status: "pendiente_decision",
        changed_by_name: null,
        changed_at: "2026-09-08T10:05:00Z",
        note: null,
      },
    ],
    ...overrides,
  };
}

const presentation = {
  presented_at: "2026-09-18",
  amount: 179800000,
  currency: "ARS",
  channel: "compr_ar",
  offer_number: "OF-2026-0871",
  notes: null,
  receipt_filename: null,
  updated_at: "2026-09-18T12:00:00Z",
};

function renderTab(props: Partial<React.ComponentProps<typeof EstadoTab>> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <EstadoTab analysisId="analysis-1" businessStatus="pendiente_decision" {...props} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("EstadoTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("muestra la decisión pendiente y aprueba pasando a En revisión cuando no hay fase 2 por lanzar", async () => {
    mockGetBusinessState.mockResolvedValue(buildState("pendiente_decision"));
    mockUpdateBusinessStatus.mockResolvedValue({
      id: "analysis-1",
      business_status: "en_revision",
      previous_status: "pendiente_decision",
      changed_by_name: "Test User",
      changed_at: "2026-09-29T10:00:00Z",
      message: "ok",
    });
    const user = userEvent.setup();
    renderTab();

    expect(await screen.findByTestId("business-decision-panel")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Aprobar y analizar Fase 2/ }));

    await waitFor(() =>
      expect(mockUpdateBusinessStatus).toHaveBeenCalledWith("analysis-1", { business_status: "en_revision" }),
    );
  });

  it("delega la aprobación al flujo de categorías cuando corresponde", async () => {
    mockGetBusinessState.mockResolvedValue(buildState("pendiente_decision"));
    const onApproveCategories = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderTab({ canStartCategories: true, onApproveCategories, onRejectCategories: vi.fn() });

    await user.click(await screen.findByRole("button", { name: /Aprobar y analizar Fase 2/ }));

    await waitFor(() => expect(onApproveCategories).toHaveBeenCalledTimes(1));
    expect(mockUpdateBusinessStatus).not.toHaveBeenCalled();
  });

  it("rechaza con motivo y avisa al flujo de categorías", async () => {
    mockGetBusinessState.mockResolvedValue(buildState("pendiente_decision"));
    mockUpdateBusinessStatus.mockResolvedValue({
      id: "analysis-1",
      business_status: "no_aprobada",
      previous_status: "pendiente_decision",
      changed_by_name: "Test User",
      changed_at: "2026-09-29T10:00:00Z",
      message: "ok",
    });
    const onRejectCategories = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderTab({ canStartCategories: true, onApproveCategories: vi.fn(), onRejectCategories });

    await user.click(await screen.findByRole("button", { name: "No aprobar" }));
    await user.type(screen.getByLabelText("Motivo (opcional)"), "Fuera de alcance");
    await user.click(screen.getByRole("button", { name: "Confirmar: no aprobar" }));

    await waitFor(() =>
      expect(mockUpdateBusinessStatus).toHaveBeenCalledWith("analysis-1", {
        business_status: "no_aprobada",
        note: "Fuera de alcance",
      }),
    );
    await waitFor(() => expect(onRejectCategories).toHaveBeenCalledTimes(1));
  });

  it("muestra el motivo de no aprobación y permite reabrir la decisión", async () => {
    mockGetBusinessState.mockResolvedValue(
      buildState("no_aprobada", {
        history: [
          {
            previous_status: "pendiente_decision",
            new_status: "no_aprobada",
            changed_by_name: "M. Fernández",
            changed_at: "2026-09-09T10:00:00Z",
            note: "Monto fuera del alcance",
          },
        ],
      }),
    );
    mockUpdateBusinessStatus.mockResolvedValue({
      id: "analysis-1",
      business_status: "pendiente_decision",
      previous_status: "no_aprobada",
      changed_by_name: "Test User",
      changed_at: "2026-09-29T10:00:00Z",
      message: "ok",
    });
    const user = userEvent.setup();
    renderTab({ businessStatus: "no_aprobada" });

    const card = await screen.findByTestId("business-no-aprobada-card");
    expect(within(card).getByText("Monto fuera del alcance")).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Reabrir decisión" }));

    await waitFor(() =>
      expect(mockUpdateBusinessStatus).toHaveBeenCalledWith("analysis-1", {
        business_status: "pendiente_decision",
      }),
    );
  });

  it("registra la presentación desde En revisión", async () => {
    mockGetBusinessState.mockResolvedValue(buildState("en_revision"));
    mockSavePresentation.mockResolvedValue(
      buildState("presentada", { presentation: { ...presentation, presented_at: todayIso() } }),
    );
    const user = userEvent.setup();
    renderTab({ businessStatus: "en_revision" });

    await user.click(await screen.findByRole("button", { name: /Registrar presentación/ }));
    await user.type(screen.getByLabelText("Monto ofertado", { selector: "input" }), "18500000");
    await user.type(screen.getByLabelText("N° de oferta / comprobante"), "OF-1");
    await user.click(screen.getByRole("button", { name: "Guardar presentación" }));

    await waitFor(() =>
      expect(mockSavePresentation).toHaveBeenCalledWith("analysis-1", {
        presented_at: todayIso(),
        amount: 18500000,
        currency: "ARS",
        channel: "compr_ar",
        offer_number: "OF-1",
        notes: null,
      }),
    );
    expect(await screen.findByTestId("presentation-summary")).toBeInTheDocument();
  });

  it("adjunta la constancia al registrar la presentación", async () => {
    mockGetBusinessState.mockResolvedValue(buildState("en_revision"));
    mockSavePresentation.mockResolvedValue(buildState("presentada", { presentation }));
    mockUploadReceipt.mockResolvedValue(
      buildState("presentada", { presentation: { ...presentation, receipt_filename: "constancia.pdf" } }),
    );
    const user = userEvent.setup();
    renderTab({ businessStatus: "en_revision" });

    await user.click(await screen.findByRole("button", { name: /Registrar presentación/ }));
    expect(screen.getByRole("combobox", { name: "Moneda" })).toHaveClass("w-[74px]");
    const file = new File(["%PDF"], "constancia.pdf", { type: "application/pdf" });
    await user.upload(screen.getByTestId("presentation-receipt-input"), file);
    expect(screen.getByTestId("presentation-receipt-chip")).toHaveTextContent("constancia.pdf");
    await user.click(screen.getByRole("button", { name: "Guardar presentación" }));

    await waitFor(() => expect(mockUploadReceipt).toHaveBeenCalledWith("analysis-1", file));
    expect(await screen.findByTestId("presentation-receipt-link")).toHaveTextContent("constancia.pdf");
  });

  it("quita la constancia existente al editar la presentación", async () => {
    const withReceipt = { ...presentation, receipt_filename: "constancia.pdf" };
    mockGetBusinessState.mockResolvedValue(buildState("presentada", { presentation: withReceipt }));
    mockSavePresentation.mockResolvedValue(buildState("presentada", { presentation: withReceipt }));
    mockDeleteReceipt.mockResolvedValue(buildState("presentada", { presentation }));
    const user = userEvent.setup();
    renderTab({ businessStatus: "presentada" });

    await user.click(await screen.findByRole("button", { name: "Editar" }));
    await user.click(screen.getByRole("button", { name: "Quitar archivo" }));
    await user.click(screen.getByRole("button", { name: "Guardar presentación" }));

    await waitFor(() => expect(mockDeleteReceipt).toHaveBeenCalledWith("analysis-1"));
    expect(mockUploadReceipt).not.toHaveBeenCalled();
  });

  it("abre la constancia adjunta desde el resumen", async () => {
    mockGetBusinessState.mockResolvedValue(
      buildState("presentada", { presentation: { ...presentation, receipt_filename: "constancia.pdf" } }),
    );
    mockReceiptLink.mockResolvedValue({ url: "https://storage.test/constancia.pdf", filename: "constancia.pdf" });
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    const user = userEvent.setup();
    renderTab({ businessStatus: "presentada" });

    await user.click(await screen.findByTestId("presentation-receipt-link"));

    await waitFor(() =>
      expect(openSpy).toHaveBeenCalledWith("https://storage.test/constancia.pdf", "_blank", "noopener,noreferrer"),
    );
    openSpy.mockRestore();
  });

  it("muestra la presentación registrada y registra una licitación perdida", async () => {
    mockGetBusinessState.mockResolvedValue(buildState("presentada", { presentation }));
    mockSaveResult.mockResolvedValue(
      buildState("perdida", {
        presentation,
        result: {
          outcome: "perdida",
          resulted_at: todayIso(),
          awarded_amount: null,
          loss_reason: "precio",
          winner_name: "Telco Andina S.A.",
          winner_amount: 171200000,
          notes: null,
          updated_at: "2026-10-05T12:00:00Z",
        },
      }),
    );
    const user = userEvent.setup();
    renderTab({ businessStatus: "presentada" });

    const summary = await screen.findByTestId("presentation-summary");
    expect(within(summary).getByText("$ 179.800.000")).toBeInTheDocument();
    expect(within(summary).getByText("COMPR.AR")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Registrar resultado" }));
    expect(screen.getByRole("button", { name: "Guardar resultado" })).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: /Perdida/ }));
    await user.type(screen.getByLabelText("Adjudicatario"), "Telco Andina S.A.");
    await user.type(screen.getByLabelText("Monto adjudicado al ganador"), "171200000");
    await user.click(screen.getByRole("button", { name: "Guardar resultado" }));

    await waitFor(() =>
      expect(mockSaveResult).toHaveBeenCalledWith("analysis-1", {
        outcome: "perdida",
        resulted_at: todayIso(),
        awarded_amount: null,
        loss_reason: "precio",
        winner_name: "Telco Andina S.A.",
        winner_amount: 171200000,
        notes: null,
      }),
    );
    const resultSummary = await screen.findByTestId("result-summary");
    expect(within(resultSummary).getByText("Precio")).toBeInTheDocument();
  });

  it("muestra la diferencia contra lo ofertado en una licitación ganada", async () => {
    mockGetBusinessState.mockResolvedValue(
      buildState("ganada", {
        presentation,
        result: {
          outcome: "ganada",
          resulted_at: "2026-10-05",
          awarded_amount: 179000000,
          loss_reason: null,
          winner_name: null,
          winner_amount: null,
          notes: "Adjudicada",
          updated_at: "2026-10-05T12:00:00Z",
        },
      }),
    );
    renderTab({ businessStatus: "ganada" });

    const summary = await screen.findByTestId("result-summary");
    expect(within(summary).getByText("$ 179.000.000")).toBeInTheDocument();
    expect(within(summary).getByText("$ 800.000 menos")).toBeInTheDocument();
    expect(within(summary).getByText("Adjudicada")).toBeInTheDocument();
  });

  it("no permite cambiar el tipo de resultado al corregirlo", async () => {
    mockGetBusinessState.mockResolvedValue(
      buildState("ganada", {
        presentation,
        result: {
          outcome: "ganada",
          resulted_at: "2026-10-05",
          awarded_amount: 179000000,
          loss_reason: null,
          winner_name: null,
          winner_amount: null,
          notes: null,
          updated_at: "2026-10-05T12:00:00Z",
        },
      }),
    );
    const user = userEvent.setup();
    renderTab({ businessStatus: "ganada" });

    await user.click(await screen.findByRole("button", { name: "Corregir resultado" }));

    expect(screen.getByRole("radio", { name: /Perdida/ })).toBeDisabled();
    expect(screen.getByRole("radio", { name: /Ganada/ })).toBeEnabled();
  });

  it("coloca el historial a la derecha cuando no se pide debajo y debajo cuando sí", async () => {
    mockGetBusinessState.mockResolvedValue(buildState("pendiente_decision"));
    const { rerender } = renderTab();

    const history = await screen.findByTestId("business-status-history");
    expect(history.className).toContain("min-[1100px]:w-[320px]");
    expect(history.parentElement?.className).toContain("min-[1100px]:flex-row");

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <ToastProvider>
          <EstadoTab analysisId="analysis-1" businessStatus="pendiente_decision" historyBelow />
        </ToastProvider>
      </QueryClientProvider>,
    );

    const stacked = await screen.findByTestId("business-status-history");
    expect(stacked.className).not.toContain("min-[1100px]:w-[320px]");
    expect(stacked.parentElement?.className).not.toContain("min-[1100px]:flex-row");
  });

  it("lista el historial de estados", async () => {
    mockGetBusinessState.mockResolvedValue(buildState("pendiente_decision"));
    renderTab();

    const history = await screen.findByTestId("business-status-history");
    await waitFor(() => expect(within(history).getByText("Análisis Fase 1 completado")).toBeInTheDocument());
    expect(within(history).getByText("Análisis iniciado")).toBeInTheDocument();
  });
});
