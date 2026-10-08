import { FileText, Send } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Button } from "../../components/Button";
import { useToast } from "../../components/ToastContainer";
import { getPresentationReceiptLink } from "../../api/businessStatus";
import type { BusinessStatus, PresentationPayload, ResultPayload } from "../../types/businessStatus";
import { BusinessDecisionPanel } from "./components/BusinessDecisionPanel";
import { BusinessStatusHistory } from "./components/BusinessStatusHistory";
import { BusinessStatusStepper } from "./components/BusinessStatusStepper";
import { PresentationForm } from "./components/PresentationForm";
import { ResultForm } from "./components/ResultForm";
import { useBusinessDecisionActions } from "./hooks/useBusinessDecisionActions";
import {
  useBusinessState,
  type ReceiptChange,
  useSavePresentation,
  useSaveResult,
  useUpdateBusinessStatus,
} from "./hooks/useBusinessState";
import {
  BUSINESS_STATUS_META,
  describeAmountDifference,
  formatIsoDate,
  formatMoney,
  getChannelLabel,
  getLossReasonLabel,
  resolveBusinessStatus,
} from "./utils/businessStatus";

interface EstadoTabProps {
  analysisId: string;
  businessStatus?: string | null;
  canStartCategories?: boolean;
  historyBelow?: boolean;
  categoriesDecisionLoading?: boolean;
  onApproveCategories?: () => Promise<void> | void;
  onRejectCategories?: () => Promise<void> | void;
}

interface FactProps {
  label: string;
  value: string;
}

function FactGrid({ facts }: { facts: FactProps[] }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-4">
      {facts.map((fact) => (
        <div key={fact.label} className="min-w-0">
          <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-[rgba(0,60,107,.55)]">
            {fact.label}
          </div>
          <div className="mt-[3px] break-words font-display text-base font-semibold text-[#003C6B]">
            {fact.value}
          </div>
        </div>
      ))}
    </div>
  );
}

type ActionTone = "neutral" | "revision" | "presentada";

const ACTION_TONE_STYLES: Record<ActionTone, { card: string; eyebrow: string }> = {
  neutral: {
    card: "border-[rgba(0,60,107,.12)] bg-white",
    eyebrow: "text-[rgba(0,60,107,.55)]",
  },
  revision: {
    card: "border-[rgba(169,102,255,.4)] bg-[rgba(169,102,255,.06)]",
    eyebrow: "text-[#6E2FC9]",
  },
  presentada: {
    card: "border-[rgba(47,78,248,.35)] bg-[rgba(47,78,248,.05)]",
    eyebrow: "text-[#2F4EF8]",
  },
};

interface ActionCardProps {
  eyebrow: string;
  title: string;
  description: string;
  tone?: ActionTone;
  children?: ReactNode;
  testId?: string;
}

function ActionCard({ eyebrow, title, description, tone = "neutral", children, testId }: ActionCardProps) {
  const styles = ACTION_TONE_STYLES[tone];
  return (
    <section
      className={`flex flex-wrap items-center justify-between gap-4 rounded-2xl border px-6 py-5 ${styles.card}`}
      data-testid={testId}
    >
      <div className="min-w-0 max-w-[560px]">
        <span className={`text-[11px] font-bold uppercase tracking-[0.14em] ${styles.eyebrow}`}>{eyebrow}</span>
        <h3 className="mt-1.5 font-display text-lg font-bold text-[#003C6B]">{title}</h3>
        <p className="mt-1.5 text-[13px] leading-normal text-[rgba(0,60,107,.68)]">{description}</p>
      </div>
      {children}
    </section>
  );
}

const OUTLINE_BUTTON_CLASS =
  "inline-flex h-10 items-center rounded-full border-[1.5px] border-[rgba(0,60,107,.2)] bg-white px-[18px] text-[13px] font-semibold text-[#003C6B] hover:border-[#0099DB] disabled:opacity-40";

const GRADIENT_BUTTON_CLASS =
  "inline-flex h-11 items-center gap-2 rounded-full bg-[linear-gradient(90deg,#2F4EF8,#A966FF)] px-[22px] text-sm font-semibold text-white hover:brightness-110";

const NAVY_BUTTON_CLASS =
  "inline-flex h-11 items-center rounded-full bg-[#003C6B] px-[22px] text-sm font-semibold text-white transition-colors hover:bg-[#0099DB]";

export function EstadoTab({
  analysisId,
  businessStatus,
  canStartCategories = false,
  historyBelow = false,
  categoriesDecisionLoading = false,
  onApproveCategories,
  onRejectCategories,
}: EstadoTabProps) {
  const { addToast } = useToast();
  const stateQuery = useBusinessState(analysisId);
  const updateStatus = useUpdateBusinessStatus();
  const savePresentation = useSavePresentation();
  const saveResult = useSaveResult();
  const [form, setForm] = useState<"presentation" | "result" | null>(null);
  const { handleApprove, handleReject, isPending: isDecisionPending } = useBusinessDecisionActions({
    analysisId,
    canStartCategories,
    onApproveCategories,
    onRejectCategories,
  });

  const state = stateQuery.data;
  const status: BusinessStatus = resolveBusinessStatus(state?.business_status ?? businessStatus);
  const presentation = state?.presentation ?? null;
  const result = state?.result ?? null;
  const history = state?.history ?? [];
  const isBusy = isDecisionPending || categoriesDecisionLoading;

  const handleReopen = async () => {
    try {
      await updateStatus.mutateAsync({ analysisId, payload: { business_status: "pendiente_decision" } });
      addToast("success", "Decisión reabierta.");
    } catch {
      addToast("error", "No se pudo reabrir la decisión.");
    }
  };

  const handleOpenReceipt = async () => {
    try {
      const link = await getPresentationReceiptLink(analysisId);
      window.open(link.url, "_blank", "noopener,noreferrer");
    } catch {
      addToast("error", "No se pudo abrir la constancia.");
    }
  };

  const handleSavePresentation = async (payload: PresentationPayload, receipt: ReceiptChange) => {
    try {
      await savePresentation.mutateAsync({ analysisId, payload, receipt });
      setForm(null);
      addToast("success", "Presentación registrada.");
    } catch {
      addToast("error", "No se pudo guardar la presentación.");
    }
  };

  const handleSaveResult = async (payload: ResultPayload) => {
    try {
      await saveResult.mutateAsync({ analysisId, payload });
      setForm(null);
      addToast("success", "Resultado registrado.");
    } catch {
      addToast("error", "No se pudo guardar el resultado.");
    }
  };

  if (stateQuery.isLoading) {
    return (
      <p className="text-sm text-[rgba(0,60,107,.68)]" data-testid="estado-tab-loading">
        Cargando estado de la licitación...
      </p>
    );
  }

  if (stateQuery.isError && !state) {
    return (
      <div
        className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[rgba(0,60,107,.12)] bg-white px-6 py-5"
        data-testid="estado-tab-error"
      >
        <p className="text-sm text-error">No se pudo cargar el estado de la licitación.</p>
        <Button type="button" variant="secondary" onClick={() => void stateQuery.refetch()}>
          Reintentar
        </Button>
      </div>
    );
  }

  const noApprovalNote = [...history].reverse().find((item) => item.new_status === "no_aprobada")?.note;
  const hasPresented = status === "presentada" || status === "ganada" || status === "perdida";
  const hasResult = status === "ganada" || status === "perdida";
  const resultMeta = BUSINESS_STATUS_META[status];

  return (
    <div className="flex flex-col gap-4" data-testid="estado-tab-content">
      <BusinessStatusStepper status={status} presentedAt={presentation?.presented_at} />

      <div
        className={`flex flex-col gap-5 ${historyBelow ? "" : "min-[1100px]:flex-row min-[1100px]:items-start"}`}
      >
        <div className="flex min-w-0 flex-1 flex-col gap-4 min-[1100px]:min-w-0">
          {status === "pendiente_decision" ? (
            <BusinessDecisionPanel
              loading={isBusy}
              onApprove={handleApprove}
              onReject={handleReject}
            />
          ) : null}

          {status === "no_aprobada" ? (
            <ActionCard
              eyebrow="No aprobada"
              title="Esta licitación no sigue al análisis completo"
              description={noApprovalNote || "Sin motivo registrado."}
              testId="business-no-aprobada-card"
            >
              <button
                type="button"
                onClick={() => void handleReopen()}
                disabled={updateStatus.isPending}
                className={OUTLINE_BUTTON_CLASS}
              >
                Reabrir decisión
              </button>
            </ActionCard>
          ) : null}

          {status === "en_revision" && form !== "presentation" ? (
            <ActionCard
              eyebrow="En revisión"
              title="Revisá el análisis y preparate para presentar"
              description="Cuando presentes la oferta en el portal, registralo acá para llevar el seguimiento del resultado."
              tone="revision"
              testId="business-revision-card"
            >
              <button type="button" onClick={() => setForm("presentation")} className={GRADIENT_BUTTON_CLASS}>
                <Send className="h-4 w-4" aria-hidden="true" />
                Registrar presentación
              </button>
            </ActionCard>
          ) : null}

          {form === "presentation" ? (
            <PresentationForm
              initial={presentation}
              saving={savePresentation.isPending}
              onSubmit={handleSavePresentation}
              onCancel={() => setForm(null)}
            />
          ) : null}

          {hasPresented && presentation && form !== "presentation" ? (
            <section
              className="flex flex-col gap-3.5 rounded-2xl border border-[rgba(0,60,107,.12)] bg-white px-6 py-5"
              data-testid="presentation-summary"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-[#2F4EF8]">
                  Presentación registrada
                </span>
                {status === "presentada" ? (
                  <button
                    type="button"
                    onClick={() => setForm("presentation")}
                    className="border-0 bg-transparent p-0 text-[13px] font-semibold text-[#0099DB] hover:text-[#003C6B]"
                  >
                    Editar
                  </button>
                ) : null}
              </div>
              <FactGrid
                facts={[
                  { label: "Fecha", value: formatIsoDate(presentation.presented_at) },
                  { label: "Monto ofertado", value: formatMoney(presentation.amount, presentation.currency) },
                  { label: "Canal", value: getChannelLabel(presentation.channel) },
                  { label: "N° de oferta", value: presentation.offer_number || "—" },
                ]}
              />
              {presentation.receipt_filename ? (
                <button
                  type="button"
                  onClick={() => void handleOpenReceipt()}
                  className="inline-flex items-center gap-2 self-start rounded-full border border-[rgba(0,60,107,.12)] bg-[#F4F9FC] px-3.5 py-1.5 text-[13px] font-semibold text-[#003C6B] hover:border-[#0099DB]"
                  data-testid="presentation-receipt-link"
                >
                  <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                  {presentation.receipt_filename}
                </button>
              ) : null}
              {presentation.notes ? (
                <p className="text-[13px] leading-normal text-[rgba(0,60,107,.68)]">{presentation.notes}</p>
              ) : null}
            </section>
          ) : null}

          {status === "presentada" && !presentation && form !== "presentation" ? (
            <ActionCard
              eyebrow="Presentación"
              title="Faltan los datos de la presentación"
              description="Completá fecha, monto y canal para dejar el registro completo."
              testId="business-missing-presentation-card"
            >
              <button type="button" onClick={() => setForm("presentation")} className={OUTLINE_BUTTON_CLASS}>
                Cargar datos
              </button>
            </ActionCard>
          ) : null}

          {status === "presentada" && form !== "result" ? (
            <ActionCard
              eyebrow="Esperando resultado"
              title="¿Ya se conoce la adjudicación?"
              description="Registrá si la ganaste o la perdiste. Así alimenta los indicadores del Home."
              tone="presentada"
              testId="business-awaiting-result-card"
            >
              <button type="button" onClick={() => setForm("result")} className={NAVY_BUTTON_CLASS}>
                Registrar resultado
              </button>
            </ActionCard>
          ) : null}

          {form === "result" ? (
            <ResultForm
              initial={result}
              presentation={presentation}
              saving={saveResult.isPending}
              onSubmit={handleSaveResult}
              onCancel={() => setForm(null)}
            />
          ) : null}

          {hasResult && result && form !== "result" ? (
            <section
              className="flex flex-col gap-3.5 rounded-2xl border px-6 py-5"
              style={{
                borderColor: status === "ganada" ? "rgba(31,201,168,.5)" : "rgba(0,60,107,.2)",
                background: status === "ganada" ? "rgba(127,243,222,.14)" : "#fff",
              }}
              data-testid="result-summary"
            >
              <div className="flex items-center justify-between gap-3">
                <span
                  className="inline-flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em]"
                  style={{ color: resultMeta.fg }}
                >
                  <span className="h-2 w-2 rounded-full" style={{ background: resultMeta.dot }} />
                  {resultMeta.label}
                </span>
                <button
                  type="button"
                  onClick={() => setForm("result")}
                  className="border-0 bg-transparent p-0 text-[13px] font-semibold text-[#0099DB] hover:text-[#003C6B]"
                >
                  Corregir resultado
                </button>
              </div>
              <FactGrid
                facts={
                  status === "ganada"
                    ? [
                        { label: "Fecha de adjudicación", value: formatIsoDate(result.resulted_at) },
                        {
                          label: "Monto adjudicado",
                          value: formatMoney(result.awarded_amount, presentation?.currency),
                        },
                        {
                          label: "Diferencia vs. oferta",
                          value: describeAmountDifference(
                            result.awarded_amount,
                            presentation?.amount,
                            presentation?.currency,
                          ),
                        },
                      ]
                    : [
                        { label: "Fecha de resultado", value: formatIsoDate(result.resulted_at) },
                        { label: "Motivo", value: getLossReasonLabel(result.loss_reason) },
                        { label: "Adjudicatario", value: result.winner_name || "—" },
                        {
                          label: "Monto ganador",
                          value: formatMoney(result.winner_amount, presentation?.currency),
                        },
                      ]
                }
              />
              {result.notes ? (
                <p className="text-[13px] leading-normal text-[rgba(0,60,107,.68)]">{result.notes}</p>
              ) : null}
            </section>
          ) : null}

          {status === "en_analisis" ? (
            <ActionCard
              eyebrow="En análisis"
              title="El análisis de Fase 1 todavía está en curso"
              description="Cuando termine, vas a poder decidir si seguís con el análisis completo."
              testId="business-en-analisis-card"
            />
          ) : null}
        </div>

        <BusinessStatusHistory items={history} stacked={historyBelow} />
      </div>
    </div>
  );
}
