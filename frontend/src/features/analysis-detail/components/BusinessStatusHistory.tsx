import type { BusinessStatusHistoryItem } from "../../../types/businessStatus";
import { BUSINESS_STATUS_META, formatDateTime } from "../utils/businessStatus";
import { SECTION_LABEL_CLASS } from "./BusinessFormFields";

interface BusinessStatusHistoryProps {
  items: BusinessStatusHistoryItem[];
  stacked?: boolean;
}

function describeEntry(item: BusinessStatusHistoryItem): string {
  switch (item.new_status) {
    case "en_analisis":
      return "Análisis iniciado";
    case "pendiente_decision":
      return item.previous_status === "no_aprobada" ? "Decisión reabierta" : "Análisis Fase 1 completado";
    case "en_revision":
      return "Aprobada · pasó a En revisión";
    default:
      return BUSINESS_STATUS_META[item.new_status]?.label ?? item.new_status;
  }
}

export function BusinessStatusHistory({ items, stacked = false }: BusinessStatusHistoryProps) {
  return (
    <aside
      aria-label="Historial de estados"
      className={`w-full flex-shrink-0 rounded-2xl border border-[rgba(0,60,107,.12)] bg-white px-5 py-[18px] ${
        stacked ? "" : "min-[1100px]:w-[320px]"
      }`}
      data-testid="business-status-history"
    >
      <span className={SECTION_LABEL_CLASS}>Historial de estados</span>
      {items.length === 0 ? (
        <p className="mt-3 text-[13px] text-[rgba(0,60,107,.55)]">Todavía no hay cambios de estado registrados.</p>
      ) : (
        <ol className="mt-3 flex flex-col">
          {items.map((item, index) => {
            const dot = BUSINESS_STATUS_META[item.new_status]?.dot ?? "#0099DB";
            const isLast = index === items.length - 1;
            return (
              <li key={`${item.new_status}-${item.changed_at}-${index}`} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <span className="mt-1.5 h-2.5 w-2.5 flex-shrink-0 rounded-full" style={{ background: dot }} />
                  {isLast ? null : <span className="mt-1 w-0.5 flex-1 bg-[rgba(0,60,107,.12)]" />}
                </div>
                <div className={isLast ? "pb-0" : "pb-4"}>
                  <div className="text-[13px] font-semibold text-[#003C6B]">{describeEntry(item)}</div>
                  <div className="text-xs text-[rgba(0,60,107,.55)]">
                    {formatDateTime(item.changed_at)} · {item.changed_by_name ?? "Sistema"}
                  </div>
                  {item.note ? <div className="mt-1 text-xs text-[rgba(0,60,107,.68)]">{item.note}</div> : null}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </aside>
  );
}
