import { useEffect, useState, type ReactNode } from "react";
import { ChevronRight, Pencil, X } from "lucide-react";

import { Button } from "../../components/Button";
import { Input } from "../../components/Input";
import { SourceEyeButton } from "./components/SourceEyeButton";
import type { AnalysisDetail, Citation, NarrativeSource } from "./types";
import { buildAnalysisShortTitle, getFieldItem, getFieldValue } from "./utils/analysisFields";
import { BUSINESS_STATUS_META, resolveBusinessStatus } from "./utils/businessStatus";

function formatDate(dateIso: string): string {
  const date = new Date(dateIso);
  if (Number.isNaN(date.getTime())) {
    return "Fecha no disponible";
  }
  return new Intl.DateTimeFormat("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

interface AnalysisDetailHeaderProps {
  analysis: AnalysisDetail;
  rightActions?: ReactNode;
  showStartTrackingAction?: boolean;
  startTrackingLabel?: string;
  startTrackingLoading?: boolean;
  onStartTracking?: () => void;
  onViewSource?: (payload: { citation: Citation; citations: Citation[]; sources: NarrativeSource[] }) => void;
  onEditPresupuesto?: (payload: { monto_estimado: number; moneda: string }) => Promise<void>;
  isEditingPresupuesto?: boolean;
  onOpenEstado?: () => void;
}

function parsePresupuestoToForm(value: string | null): { monto: string; moneda: string } {
  if (!value) {
    return { monto: "", moneda: "ARS" };
  }

  const text = value.trim();
  const currency = /u\$s|us\$|usd|d[oó]lares?/i.test(text)
    ? "USD"
    : /ars|\$/i.test(text)
      ? "ARS"
      : "ARS";

  const amountMatch = text.match(/\d{1,3}(?:[.\s]\d{3})+(?:,\d+)?|\d+,\d+|\d+\.\d{1,2}(?!\d)|\d+/);
  if (!amountMatch) {
    return { monto: "", moneda: currency };
  }

  const raw = amountMatch[0].replace(/\s/g, "");
  let normalized = raw;
  if (raw.includes(",")) {
    normalized = raw.replace(/\./g, "").replace(",", ".");
  } else if (!/^\d+\.\d{1,2}$/.test(raw)) {
    normalized = raw.replace(/\./g, "");
  }

  const parsed = Number(normalized);
  if (!Number.isFinite(parsed)) {
    return { monto: "", moneda: currency };
  }

  return {
    monto: String(Math.trunc(parsed)),
    moneda: currency,
  };
}

function formatThousandsWithDots(rawDigits: string): string {
  const digits = rawDigits.replace(/\D/g, "");
  if (!digits) {
    return "";
  }
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

export function AnalysisDetailHeader({
  analysis,
  rightActions,
  showStartTrackingAction = false,
  startTrackingLabel = "Iniciar seguimiento",
  startTrackingLoading = false,
  onStartTracking,
  onViewSource,
  onEditPresupuesto,
  isEditingPresupuesto = false,
  onOpenEstado,
}: AnalysisDetailHeaderProps) {
  const totalPages = analysis.documents.reduce((sum, doc) => sum + (doc.page_count || 0), 0);

  const organismo = getFieldValue(analysis, "datos_procedimiento", "Organismo convocante");
  const expediente = getFieldValue(analysis, "datos_procedimiento", "Expediente");
  const procedimiento = getFieldValue(analysis, "datos_procedimiento", "Procedimiento");
  const tipoProcedimiento = getFieldValue(analysis, "datos_procedimiento", "Tipo de procedimiento");
  const denominacion = getFieldValue(analysis, "datos_procedimiento", "Denominación");
  const presupuestoOficialItem = getFieldItem(analysis, "datos_procedimiento", "Presupuesto oficial");
  const presupuestoOficial = presupuestoOficialItem?.field_value ?? null;
  const presupuestoCitations = presupuestoOficialItem?.citations ?? [];
  const [showEditBudgetModal, setShowEditBudgetModal] = useState(false);
  const [montoInput, setMontoInput] = useState("");
  const [monedaInput, setMonedaInput] = useState("ARS");
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!showEditBudgetModal) {
      return;
    }
    const parsed = parsePresupuestoToForm(presupuestoOficial);
    setMontoInput(formatThousandsWithDots(parsed.monto));
    setMonedaInput(parsed.moneda);
    setFormError(null);
  }, [showEditBudgetModal, presupuestoOficial]);

  const handleViewPresupuestoSource = () => {
    if (!onViewSource || presupuestoCitations.length === 0) {
      return;
    }
    const sources: NarrativeSource[] = presupuestoCitations.map((citation, index) => ({ id: index, ...citation }));
    onViewSource({ citation: presupuestoCitations[0], citations: presupuestoCitations, sources });
  };

  const handleSaveManualBudget = async () => {
    if (!onEditPresupuesto || isEditingPresupuesto) {
      return;
    }

    const montoDigits = montoInput.replace(/\D/g, "");
    const monto = Number(montoDigits);
    if (!montoDigits || !Number.isFinite(monto) || monto < 0) {
      setFormError("Ingresá un monto válido mayor o igual a 0.");
      return;
    }

    const moneda = monedaInput.trim().toUpperCase();
    if (!moneda) {
      setFormError("Ingresá una moneda.");
      return;
    }

    setFormError(null);
    await onEditPresupuesto({ monto_estimado: monto, moneda });
    setShowEditBudgetModal(false);
  };

  const title = buildAnalysisShortTitle(analysis);
  // Sin tipo/número/denominación, `buildAnalysisShortTitle` cae al organismo -- no lo repetimos en el subtítulo.
  const titleUsesOrganismo = !tipoProcedimiento && !procedimiento && !denominacion && Boolean(organismo);
  const subtitle = (titleUsesOrganismo ? [expediente] : [organismo, expediente]).filter(Boolean).join(" · ");
  const businessUnit = analysis.business_unit?.trim() || "Unidad pendiente";
  const hasBusinessStatus = Boolean(analysis.business_status?.trim());
  const businessStatusMeta = BUSINESS_STATUS_META[resolveBusinessStatus(analysis.business_status)];
  const businessStatusLabel = hasBusinessStatus ? businessStatusMeta.label : "Estado negocio pendiente";
  const documentsCount = analysis.documents.length;

  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <div className="mb-[10px] flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-[7px] rounded-full border border-[rgba(0,60,107,.12)] bg-white px-3 py-[5px] text-xs font-semibold text-[#003C6B]">
            <span className="h-2 w-2 rounded-full bg-[#0099DB]" aria-hidden="true" />
            {businessUnit}
          </span>
          {onOpenEstado ? (
            <button
              type="button"
              onClick={onOpenEstado}
              title="Ver estado y resultado"
              data-testid="business-status-badge"
              className="inline-flex items-center gap-1.5 rounded-full border-0 px-3 py-[5px] text-xs font-bold"
              style={{ background: businessStatusMeta.bg, color: businessStatusMeta.fg }}
            >
              {businessStatusLabel}
              <ChevronRight className="h-3 w-3" aria-hidden="true" />
            </button>
          ) : (
            <span
              data-testid="business-status-badge"
              className="inline-flex rounded-full px-3 py-[5px] text-xs font-bold"
              style={{ background: businessStatusMeta.bg, color: businessStatusMeta.fg }}
            >
              {businessStatusLabel}
            </span>
          )}
          <span className="text-xs text-[rgba(0,60,107,.55)]">
            {formatDate(analysis.created_at)} · {totalPages} {totalPages === 1 ? "página" : "páginas"} · {documentsCount} {documentsCount === 1 ? "documento" : "documentos"}
            {analysis.created_by_name ? ` · creado por ${analysis.created_by_name}` : ""}
          </span>
        </div>

        <h1 className="font-display text-[26px] font-bold leading-[1.15] tracking-[-0.015em] text-[#003C6B]">{title}</h1>
        {subtitle ? <p className="mt-1.5 text-sm text-[rgba(0,60,107,.68)]">{subtitle}</p> : null}
      </div>

      <div className="text-right">
        <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-[rgba(0,60,107,.55)]">Presupuesto oficial</div>
        <div className="mt-1 flex items-center justify-end gap-1.5">
          <span className="font-display text-2xl font-bold tracking-[-0.02em] text-[#003C6B]">{presupuestoOficial || "—"}</span>
          {presupuestoCitations.length > 0 ? (
            <SourceEyeButton
              variant="icon"
              pages={presupuestoCitations.map((citation) => citation.page)}
              onClick={handleViewPresupuestoSource}
            />
          ) : null}
          <button
            type="button"
            aria-label="Editar presupuesto oficial"
            title="Editar presupuesto oficial"
            className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-0 bg-transparent text-[rgba(0,60,107,.4)] transition-colors hover:text-[#0099DB] focus:outline-none focus-visible:ring-1 focus-visible:ring-[#0099DB]"
            onClick={() => setShowEditBudgetModal(true)}
          >
            <Pencil className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        {rightActions ? <div className="mt-2 flex justify-end">{rightActions}</div> : null}
      </div>

      {showStartTrackingAction && !rightActions ? (
        <div className="w-full">
          <Button
            type="button"
            size="sm"
            onClick={onStartTracking}
            loading={startTrackingLoading}
            disabled={!onStartTracking}
          >
            {startTrackingLabel}
          </Button>
        </div>
      ) : null}

      {showEditBudgetModal ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(0,60,107,.45)] p-4"
          role="dialog"
          aria-modal="true"
          aria-label="Editar presupuesto oficial"
          onClick={() => {
            if (!isEditingPresupuesto) {
              setShowEditBudgetModal(false);
            }
          }}
        >
          <div
            className="flex w-full max-w-[460px] flex-col gap-4 rounded-[24px] border border-[rgba(0,60,107,.12)] bg-white p-6 shadow-[0_24px_60px_rgba(0,60,107,.28)]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-display text-[19px] font-bold text-[#003C6B]">Editar presupuesto oficial</h2>
                <p className="mt-0.5 text-[12.5px] text-[rgba(0,60,107,.6)]">
                  Este valor manual reemplaza el monto extraído automáticamente.
                </p>
              </div>
              <button
                type="button"
                aria-label="Cerrar edición de presupuesto"
                className="flex h-[30px] w-[30px] flex-shrink-0 items-center justify-center rounded-full border-0 bg-transparent text-[rgba(0,60,107,.45)] hover:bg-[#F4F9FC] hover:text-[#003C6B]"
                onClick={() => setShowEditBudgetModal(false)}
                disabled={isEditingPresupuesto}
              >
                <X className="h-[15px] w-[15px]" />
              </button>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <Input
                label="Monto"
                value={montoInput}
                onChange={(event) => setMontoInput(formatThousandsWithDots(event.target.value))}
                placeholder="Ej: 19.800.000"
                inputMode="numeric"
              />
              <Input
                label="Moneda"
                value={monedaInput}
                onChange={(event) => setMonedaInput(event.target.value.toUpperCase())}
                placeholder="ARS o USD"
                maxLength={10}
              />
            </div>

            {formError ? <p className="text-xs text-error">{formError}</p> : null}

            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setShowEditBudgetModal(false)}
                disabled={isEditingPresupuesto}
              >
                Cancelar
              </Button>
              <Button type="button" onClick={() => void handleSaveManualBudget()} loading={isEditingPresupuesto}>
                Guardar
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </header>
  );
}
