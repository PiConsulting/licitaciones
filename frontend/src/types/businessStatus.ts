export type BusinessStatus =
  | "en_analisis"
  | "pendiente_decision"
  | "no_aprobada"
  | "en_revision"
  | "presentada"
  | "ganada"
  | "perdida";

export type PresentationChannel = "compr_ar" | "bac_caba" | "portal_organismo" | "mesa_entradas" | "otro";

export type LossReason = "precio" | "puntaje_tecnico" | "descalificada" | "desierta_cancelada" | "otro";

export type BusinessCurrency = "ARS" | "USD";

export type BusinessOutcome = "ganada" | "perdida";

export interface PresentationData {
  presented_at: string;
  amount: number | null;
  currency: string;
  channel: string;
  offer_number: string | null;
  notes: string | null;
  receipt_filename: string | null;
  updated_at: string;
}

export interface ReceiptLink {
  url: string;
  filename: string;
}

export interface ResultData {
  outcome: BusinessOutcome;
  resulted_at: string;
  awarded_amount: number | null;
  loss_reason: string | null;
  winner_name: string | null;
  winner_amount: number | null;
  notes: string | null;
  updated_at: string;
}

export interface BusinessStatusHistoryItem {
  previous_status: BusinessStatus | null;
  new_status: BusinessStatus;
  changed_by_name: string | null;
  changed_at: string;
  note: string | null;
}

export interface BusinessState {
  id: string;
  business_status: BusinessStatus;
  presentation: PresentationData | null;
  result: ResultData | null;
  history: BusinessStatusHistoryItem[];
}

export interface BusinessStatusUpdatePayload {
  business_status: BusinessStatus;
  note?: string;
}

export interface BusinessStatusUpdateResponse {
  id: string;
  business_status: BusinessStatus;
  previous_status: BusinessStatus | null;
  changed_by_name: string | null;
  changed_at: string;
  message: string;
}

export interface PresentationPayload {
  presented_at: string;
  amount: number | null;
  currency: BusinessCurrency;
  channel: PresentationChannel;
  offer_number: string | null;
  notes: string | null;
}

export interface ResultPayload {
  outcome: BusinessOutcome;
  resulted_at: string;
  awarded_amount: number | null;
  loss_reason: LossReason | null;
  winner_name: string | null;
  winner_amount: number | null;
  notes: string | null;
}
