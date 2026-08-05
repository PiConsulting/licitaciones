import { AxiosError } from "axios";

import apiClient from "../../api/client";
import {
  type AnalysisDetail,
  type CategoryData,
  type CategoryId,
  type FieldItem,
  type SourceReference,
} from "../../features/analysis-detail/types";
import type { AnalysisStatusResponse } from "../../types/analysis";
import { CATEGORY_ORDER } from "../../utils/categoryIcons";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function toSourceReference(value: unknown): SourceReference | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    page: Number(value.page ?? 0),
    document_id: String(value.document_id ?? ""),
    text_snippet: String(value.text_snippet ?? ""),
  };
}

function toFieldItem(value: unknown): FieldItem | null {
  if (!isRecord(value)) {
    return null;
  }

  const stateValue = String(value.field_state ?? "extraido") as FieldItem["field_state"];
  const fieldState = ["extraido", "no_encontrado", "no_aplica", "en_conflicto"].includes(stateValue)
    ? stateValue
    : "extraido";

  const citationsRaw = Array.isArray(value.citations) ? value.citations : [];

  return {
    field_name: String(value.field_name ?? "Campo sin nombre"),
    field_value: value.field_value == null ? null : String(value.field_value),
    field_state: fieldState,
    confidence: Number(value.confidence ?? 0),
    citations: citationsRaw
      .filter(isRecord)
      .map((citation) => ({
        text: String(citation.text ?? ""),
        page: Number(citation.page ?? 0),
        document_id: String(citation.document_id ?? ""),
        document_name: String(citation.document_name ?? "Documento"),
        value: citation.value == null ? undefined : String(citation.value),
      })),
    modified_by: value.modified_by == null ? undefined : String(value.modified_by),
    modified_at: value.modified_at == null ? undefined : String(value.modified_at),
  };
}

function emptyCategoryData(): CategoryData {
  return {
    items: [],
    confidence: 0,
    source_references: [],
    extraction_status: "partial",
    summary: "Sin datos extraídos todavía.",
    is_reviewed: false,
  };
}

/**
 * El backend emite cada categoría como un array de ítems y el estado agregado en
 * una clave hermana, cuyo nombre no siempre coincide con el de la categoría.
 */
const BACKEND_STATUS_KEY: Record<CategoryId, string> = {
  plazos_clave: "plazos_clave_extraction_status",
  garantias: "garantias_extraction_status",
  causales_rechazo: "causales_extraction_status",
  objeto_alcance: "objeto_alcance_extraction_status",
  requisitos_admisibilidad: "requisitos_admisibilidad_extraction_status",
  criterios_evaluacion: "criterios_extraction_status",
  anexos_obligatorios: "anexos_extraction_status",
  datos_procedimiento: "datos_procedimiento_extraction_status",
};

const FIELD_LABELS: Record<string, string> = {
  presentacion_ofertas: "Presentación de ofertas",
  apertura: "Apertura de ofertas",
  consultas: "Consultas",
  respuesta_consultas: "Respuesta a consultas",
  visita_obra: "Visita a obra",
  mantenimiento_oferta: "Mantenimiento de oferta",
  adjudicacion: "Adjudicación",
  firma_contrato: "Firma del contrato",
  inicio_ejecucion: "Inicio de ejecución",
  entrega: "Entrega",
  garantia_tecnica: "Garantía técnica",
  impugnacion: "Impugnación",
  cumplimiento_contrato: "Garantía de cumplimiento de contrato",
  anticipo: "Garantía de anticipo",
  resumen_objeto: "Objeto",
  modalidad: "Modalidad",
  oferta_parcial: "Admite oferta parcial",
  oferta_alternativa: "Admite oferta alternativa",
  lugar_entrega: "Lugar de entrega",
  plazo_ejecucion: "Plazo de ejecución",
  presupuesto_oficial: "Presupuesto oficial",
  otro: "Otro",
  otra: "Otra",
};

function humanizeTipo(tipo: string): string {
  if (!tipo) {
    return "Campo sin nombre";
  }
  if (FIELD_LABELS[tipo]) {
    return FIELD_LABELS[tipo];
  }
  const spaced = tipo.replace(/_/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

const STATE_BY_STATUS: Record<string, FieldItem["field_state"]> = {
  success: "extraido",
  partial: "extraido",
  not_found: "no_encontrado",
  failed: "no_encontrado",
  not_applicable: "no_aplica",
};

function joinParts(parts: Array<string | null | undefined>): string | null {
  const clean = parts.map((part) => (part == null ? "" : String(part).trim())).filter(Boolean);
  return clean.length > 0 ? clean.join(" · ") : null;
}

/** Deriva un valor legible según la forma del ítem (plazo, garantía o genérico). */
function backendItemValue(item: Record<string, unknown>): string | null {
  if (item.valor != null && String(item.valor).trim() !== "") {
    return String(item.valor);
  }

  // PlazoItem
  if ("fecha" in item || "expresion_relativa" in item || "texto_original" in item) {
    const fecha = item.fecha == null ? "" : String(item.fecha).trim();
    const hora = item.hora == null ? "" : String(item.hora).trim();
    const fechaHora = fecha && hora ? `${fecha} ${hora}` : fecha || "";
    const value = joinParts([
      fechaHora || null,
      fechaHora ? null : (item.expresion_relativa as string | null),
      fechaHora || item.expresion_relativa ? null : (item.texto_original as string | null),
      item.lugar == null ? null : `Lugar: ${String(item.lugar)}`,
    ]);
    if (value) {
      return value;
    }
  }

  // GarantiaItem
  if ("monto_porcentaje" in item || "monto_valor" in item || "forma_constitucion" in item) {
    const moneda = item.moneda == null ? "" : String(item.moneda).trim();
    const value = joinParts([
      item.monto_porcentaje == null ? null : `${item.monto_porcentaje}%`,
      item.monto_valor == null ? null : `${item.monto_valor}${moneda ? ` ${moneda}` : ""}`,
      item.sobre_que_se_calcula == null ? null : `Sobre: ${String(item.sobre_que_se_calcula)}`,
      item.forma_constitucion == null ? null : `Forma: ${String(item.forma_constitucion)}`,
      item.vigencia == null ? null : `Vigencia: ${String(item.vigencia)}`,
    ]);
    if (value) {
      return value;
    }
  }

  return null;
}

/** Convierte un ítem del backend (tipo/valor/source_references) en un FieldItem de UI. */
function fromBackendItem(value: unknown): FieldItem | null {
  if (!isRecord(value)) {
    return null;
  }

  const status = String(value.extraction_status ?? "success");
  const refsRaw = Array.isArray(value.source_references) ? value.source_references : [];

  return {
    field_name: humanizeTipo(String(value.tipo ?? "")),
    field_value: backendItemValue(value),
    field_state: STATE_BY_STATUS[status] ?? "extraido",
    confidence: Number(value.confidence ?? 0),
    citations: refsRaw.filter(isRecord).map((ref) => ({
      text: String(ref.citation ?? ""),
      page: Number(ref.page_number ?? 0),
      document_id: String(ref.document_id ?? ""),
      document_name: "Documento",
    })),
  };
}

function summarize(items: FieldItem[]): string {
  if (items.length === 0) {
    return "Sin datos extraídos todavía.";
  }
  const extracted = items.filter((item) => item.field_state === "extraido").length;
  const notFound = items.filter((item) => item.field_state === "no_encontrado").length;
  const notApplicable = items.filter((item) => item.field_state === "no_aplica").length;

  const parts = [`${extracted} dato${extracted === 1 ? "" : "s"} extraído${extracted === 1 ? "" : "s"}`];
  if (notFound > 0) {
    parts.push(`${notFound} no encontrado${notFound === 1 ? "" : "s"}`);
  }
  if (notApplicable > 0) {
    parts.push(`${notApplicable} no aplica${notApplicable === 1 ? "" : "n"}`);
  }
  return parts.join(" · ");
}

/** Construye CategoryData a partir del array de ítems que emite el backend. */
function fromBackendArray(
  rawItems: unknown[],
  statusFromSibling: unknown,
): CategoryData {
  const items = rawItems.map(fromBackendItem).filter((item): item is FieldItem => item !== null);

  const withConfidence = items.filter((item) => Number.isFinite(item.confidence) && item.confidence > 0);
  const confidence =
    withConfidence.length > 0
      ? withConfidence.reduce((total, item) => total + item.confidence, 0) / withConfidence.length
      : 0;

  const sourceReferences = items.flatMap((item) =>
    item.citations.map((citation) => ({
      page: citation.page,
      document_id: citation.document_id,
      text_snippet: citation.text,
    })),
  );

  const statusValue = String(statusFromSibling ?? "");
  const extractionStatus = ["success", "partial", "failed", "not_found", "not_applicable"].includes(statusValue)
    ? (statusValue as CategoryData["extraction_status"])
    : items.length > 0
      ? "success"
      : "not_found";

  return {
    items,
    confidence,
    source_references: sourceReferences,
    extraction_status: extractionStatus,
    summary: summarize(items),
    is_reviewed: false,
  };
}

function normalizeCategories(extractedData: unknown): Record<CategoryId, CategoryData> {
  const result = CATEGORY_ORDER.reduce<Record<CategoryId, CategoryData>>((acc, categoryId) => {
    acc[categoryId] = emptyCategoryData();
    return acc;
  }, {} as Record<CategoryId, CategoryData>);

  if (!isRecord(extractedData)) {
    return result;
  }

  const legacyToUiMap: Partial<Record<CategoryId, string[]>> = {
    plazos_clave: ["plazos"],
    requisitos_admisibilidad: ["documentos_requeridos", "restricciones_participacion"],
    datos_procedimiento: ["cronograma_proceso", "estimacion_presupuesto"],
  };

  for (const categoryId of CATEGORY_ORDER) {
    let rawCategory = extractedData[categoryId];

    // Forma actual del backend: la categoría es un array de ítems y el estado
    // agregado viaja en una clave hermana.
    if (Array.isArray(rawCategory)) {
      result[categoryId] = fromBackendArray(rawCategory, extractedData[BACKEND_STATUS_KEY[categoryId]]);
      continue;
    }

    if (!isRecord(rawCategory) && legacyToUiMap[categoryId]) {
      const legacyKeys = legacyToUiMap[categoryId] as string[];
      const arrayCandidates = legacyKeys
        .map((key) => extractedData[key])
        .filter((value): value is unknown[] => Array.isArray(value));

      if (arrayCandidates.length > 0) {
        result[categoryId] = fromBackendArray(
          arrayCandidates.flat(),
          extractedData[BACKEND_STATUS_KEY[categoryId]],
        );
        continue;
      }

      const candidates = legacyKeys
        .map((key) => extractedData[key])
        .filter((value) => isRecord(value));

      if (candidates.length > 0) {
        rawCategory = candidates[0];
      }
    }

    if (!isRecord(rawCategory)) {
      continue;
    }

    const rawItems = Array.isArray(rawCategory.items) ? rawCategory.items : [];
    const items = rawItems.map(toFieldItem).filter((item): item is FieldItem => item !== null);

    const rawRefs = Array.isArray(rawCategory.source_references) ? rawCategory.source_references : [];
    const refs = rawRefs
      .map(toSourceReference)
      .filter((ref): ref is SourceReference => ref !== null);

    const statusValue = String(rawCategory.extraction_status ?? "partial");
    const extractionStatus = ["success", "partial", "failed", "not_found", "not_applicable"].includes(statusValue)
      ? (statusValue as CategoryData["extraction_status"])
      : "partial";

    result[categoryId] = {
      items,
      confidence: Number(rawCategory.confidence ?? 0),
      source_references: refs,
      extraction_status: extractionStatus,
      summary: String(rawCategory.summary ?? "Sin resumen disponible."),
      is_reviewed: Boolean(rawCategory.is_reviewed),
    };
  }

  return result;
}

function mapStatusToDetail(analysisId: string, statusPayload: AnalysisStatusResponse): AnalysisDetail {
  return {
    id: analysisId,
    created_at: statusPayload.started_at ?? new Date().toISOString(),
    status: statusPayload.status,
    current_stage: statusPayload.current_stage,
    current_version: {
      id: `${analysisId}-v1`,
      version_number: 1,
      extracted_data: normalizeCategories(statusPayload.extracted_data),
      conflicts: {},
      created_at: statusPayload.started_at ?? new Date().toISOString(),
    },
    documents: [],
  };
}

export async function getAnalysisById(analysisId: string): Promise<AnalysisDetail> {
  try {
    const response = await apiClient.get<AnalysisDetail>(`/analyses/${analysisId}`);
    const payload = response.data;
    return {
      ...payload,
      current_version: {
        ...payload.current_version,
        extracted_data: normalizeCategories(payload.current_version?.extracted_data),
      },
    };
  } catch (error) {
    if (error instanceof AxiosError && error.response?.status === 404) {
      const statusResponse = await apiClient.get<AnalysisStatusResponse>(`/analyses/${analysisId}/status`);
      return mapStatusToDetail(analysisId, statusResponse.data);
    }
    throw error;
  }
}
