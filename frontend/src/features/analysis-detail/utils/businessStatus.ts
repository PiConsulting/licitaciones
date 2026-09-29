import type {
  BusinessCurrency,
  BusinessStatus,
  LossReason,
  PresentationChannel,
} from "../../../types/businessStatus";

export interface BusinessStatusMeta {
  label: string;
  bg: string;
  fg: string;
  dot: string;
}

export const BUSINESS_STATUS_META: Record<BusinessStatus, BusinessStatusMeta> = {
  en_analisis: { label: "En análisis", bg: "rgba(0,60,107,.08)", fg: "rgba(0,60,107,.68)", dot: "rgba(0,60,107,.35)" },
  pendiente_decision: { label: "Pendiente de decisión", bg: "rgba(0,153,219,.12)", fg: "#0077AD", dot: "#0099DB" },
  no_aprobada: { label: "No aprobada", bg: "rgba(0,60,107,.08)", fg: "rgba(0,60,107,.68)", dot: "rgba(0,60,107,.35)" },
  en_revision: { label: "En revisión", bg: "rgba(169,102,255,.14)", fg: "#6E2FC9", dot: "#A966FF" },
  presentada: { label: "Presentada", bg: "rgba(47,78,248,.12)", fg: "#2F4EF8", dot: "#2F4EF8" },
  ganada: { label: "Ganada", bg: "rgba(127,243,222,.3)", fg: "#0B6B58", dot: "#1FC9A8" },
  perdida: { label: "Perdida", bg: "rgba(0,60,107,.08)", fg: "rgba(0,60,107,.68)", dot: "rgba(0,60,107,.35)" },
};

const KNOWN_STATUSES = Object.keys(BUSINESS_STATUS_META) as BusinessStatus[];

export function resolveBusinessStatus(value: string | null | undefined): BusinessStatus {
  const normalized = value?.trim();
  if (normalized && (KNOWN_STATUSES as string[]).includes(normalized)) {
    return normalized as BusinessStatus;
  }
  return "en_analisis";
}

const PENDING_ACTION_TEXT: Partial<Record<BusinessStatus, string>> = {
  pendiente_decision: "Decidir si seguimos con Fase 2",
  en_revision: "Registrar la presentación cuando la hagas",
  presentada: "Registrar el resultado cuando se conozca",
};

export function getPendingActionText(status: BusinessStatus): string | null {
  return PENDING_ACTION_TEXT[status] ?? null;
}

export const PRESENTATION_CHANNEL_OPTIONS: { value: PresentationChannel; label: string }[] = [
  { value: "compr_ar", label: "COMPR.AR" },
  { value: "bac_caba", label: "BAC (CABA)" },
  { value: "portal_organismo", label: "Portal del organismo" },
  { value: "mesa_entradas", label: "Mesa de entradas" },
  { value: "otro", label: "Otro" },
];

export const LOSS_REASON_OPTIONS: { value: LossReason; label: string }[] = [
  { value: "precio", label: "Precio" },
  { value: "puntaje_tecnico", label: "Puntaje técnico" },
  { value: "descalificada", label: "Descalificada por requisito formal" },
  { value: "desierta_cancelada", label: "Licitación desierta o cancelada" },
  { value: "otro", label: "Otro" },
];

export const CURRENCY_OPTIONS: BusinessCurrency[] = ["ARS", "USD"];

export function getChannelLabel(value: string | null | undefined): string {
  return PRESENTATION_CHANNEL_OPTIONS.find((option) => option.value === value)?.label ?? value ?? "—";
}

export function getLossReasonLabel(value: string | null | undefined): string {
  return LOSS_REASON_OPTIONS.find((option) => option.value === value)?.label ?? value ?? "—";
}

export function formatIsoDate(iso: string | null | undefined): string {
  if (!iso) {
    return "—";
  }
  const [datePart] = iso.split("T");
  const [year, month, day] = datePart.split("-");
  if (!year || !month || !day) {
    return "—";
  }
  return `${day}/${month}/${year}`;
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return new Intl.DateTimeFormat("es-AR", { day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
}

export function formatMoney(amount: number | null | undefined, currency: string = "ARS"): string {
  if (amount === null || amount === undefined) {
    return "—";
  }
  const symbol = currency === "USD" ? "US$" : "$";
  return `${symbol} ${new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 }).format(amount)}`;
}

export function formatAmountInput(raw: string): string {
  const digits = raw.replace(/\D/g, "");
  if (!digits) {
    return "";
  }
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

export function parseAmountInput(raw: string): number | null {
  const digits = raw.replace(/\D/g, "");
  if (!digits) {
    return null;
  }
  return Number(digits);
}

export function amountToInput(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) {
    return "";
  }
  return formatAmountInput(String(Math.trunc(amount)));
}

export function todayIso(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

export function describeAmountDifference(
  awarded: number | null | undefined,
  offered: number | null | undefined,
  currency: string = "ARS",
): string {
  if (!awarded || !offered) {
    return "—";
  }
  if (awarded === offered) {
    return "Igual a lo ofertado";
  }
  const difference = formatMoney(Math.abs(awarded - offered), currency);
  return awarded < offered ? `${difference} menos` : `${difference} más`;
}
