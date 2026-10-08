import { AxiosError } from "axios";

import apiClient from "../../api/client";
import { dedupeNarrativeSources, remapSourceIds } from "../../features/analysis-detail/utils/dedupeCitations";
import {
  type AnalysisDetail,
  type CategoryData,
  type CategoryId,
  type CategoryNarrative,
  type ConfidenceLevel,
  type FieldItem,
  type HighlightRegion,
  type NarrativeBlockData,
  type NarrativeSource,
  type PlazoRawFields,
  type SourceReference,
} from "../../features/analysis-detail/types";
import type { AnalysisStatusResponse } from "../../types/analysis";
import { CATEGORY_ORDER } from "../../utils/categoryIcons";

let currentDocumentNameById = new Map<string, string>();

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** CTX-06: nombre de archivo de la cita; usa `filename` del backend con fallback al mapa de documentos del análisis. */
function toDocumentName(value: Record<string, unknown>): string {
  const documentId = String(value.document_id ?? "").trim();
  const fromDocuments = documentId ? currentDocumentNameById.get(documentId) : undefined;
  const fromBackend = String(value.filename ?? "").trim();
  if (fromBackend) {
    return fromBackend;
  }
  return fromDocuments || "Documento";
}

function buildDocumentNameById(documents: unknown): Map<string, string> {
  const map = new Map<string, string>();
  if (!Array.isArray(documents)) {
    return map;
  }

  for (const rawDocument of documents) {
    if (!isRecord(rawDocument)) {
      continue;
    }
    const id = String(rawDocument.id ?? "").trim();
    const filename = String(rawDocument.filename ?? "").trim();
    if (id && filename) {
      map.set(id, filename);
    }
  }

  return map;
}

function toConfidenceLevel(value: unknown): ConfidenceLevel {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (normalized === "alta" || normalized === "high") {
    return "high";
  }
  if (normalized === "media" || normalized === "medium") {
    return "medium";
  }
  return "low";
}

function toSourceIds(value: unknown): number[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((id) => Number(id)).filter((id) => Number.isFinite(id));
}

/** Coordenadas de resaltado del backend, tal cual. FIX 2026-08-14: antes no se copiaban y el resaltado por coordenadas quedaba muerto en producción. */
function toHighlightRegions(value: unknown): HighlightRegion[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const regions: HighlightRegion[] = [];
  for (const raw of value) {
    if (!isRecord(raw)) {
      continue;
    }
    const region = {
      x: Number(raw.x),
      y: Number(raw.y),
      width: Number(raw.width),
      height: Number(raw.height),
    };
    if (Object.values(region).every((n) => Number.isFinite(n))) {
      regions.push(region);
    }
  }
  return regions;
}

function toNarrativeSource(value: unknown): NarrativeSource | null {
  if (!isRecord(value)) {
    return null;
  }
  return {
    id: Number(value.id ?? 0),
    document_id: String(value.document_id ?? ""),
    document_name: toDocumentName(value),
    page: Number(value.page_number ?? 0),
    text: String(value.citation ?? ""),
    unverified: Boolean(value.unverified),
    highlight_regions: toHighlightRegions(value.highlight_regions),
  };
}

/** Convierte un bloque crudo a forma tipada; devuelve null en vez de lanzar para no tumbar el resto de la respuesta. */
function toNarrativeBlock(value: unknown): NarrativeBlockData | null {
  if (!isRecord(value)) {
    return null;
  }

  const type = String(value.type ?? "");

  if (type === "paragraph") {
    const text = String(value.text ?? "").trim();
    if (!text) {
      return null;
    }
    return {
      type: "paragraph",
      text,
      confidence_level: toConfidenceLevel(value.confidence_level),
      source_ids: toSourceIds(value.source_ids),
    };
  }

  if (type === "bullet_list") {
    const rawItems = Array.isArray(value.items) ? value.items : [];
    const items = rawItems
      .filter(isRecord)
      .map((item) => ({
        text: String(item.text ?? "").trim(),
        resumen: item.resumen == null ? undefined : String(item.resumen),
        // Bug real: nunca se leía `titulo` acá -- el backend lo sintetiza bien
        // (título corto + detalle) pero la UI caía SIEMPRE a la fila sin
        // título (bullet + primera frase en negrita), en TODAS las categorías.
        titulo: item.titulo == null ? undefined : String(item.titulo),
        confidence_level: toConfidenceLevel(item.confidence_level),
        source_ids: toSourceIds(item.source_ids),
        conflict_count: typeof item.conflict_count === "number" ? item.conflict_count : 0,
      }))
      .filter((item) => item.text !== "");
    if (items.length === 0) {
      return null;
    }
    return { type: "bullet_list", items };
  }

  if (type === "table") {
    const headers = Array.isArray(value.headers) ? value.headers.map((header) => String(header)) : [];
    const rawRows = Array.isArray(value.rows) ? value.rows : [];
    const rows = rawRows
      .filter(isRecord)
      .map((row) => ({
        cells: Array.isArray(row.cells) ? row.cells.map((cell) => String(cell)) : [],
        confidence_level: toConfidenceLevel(row.confidence_level),
        source_ids: toSourceIds(row.source_ids),
      }));
    if (headers.length === 0 || rows.length === 0) {
      return null;
    }
    return { type: "table", headers, rows };
  }

  return null;
}

/** Remapea source_ids con el mapping de la deduplicación de fuentes, para que ningún bloque apunte a un id descartado. */
function remapNarrativeBlockSourceIds(block: NarrativeBlockData, idMapping: Map<number, number>): NarrativeBlockData {
  if (block.type === "paragraph") {
    return { ...block, source_ids: remapSourceIds(block.source_ids, idMapping) };
  }
  if (block.type === "bullet_list") {
    return {
      ...block,
      items: block.items.map((item) => ({ ...item, source_ids: remapSourceIds(item.source_ids, idMapping) })),
    };
  }
  return {
    ...block,
    rows: block.rows.map((row) => ({ ...row, source_ids: remapSourceIds(row.source_ids, idMapping) })),
  };
}

/** Arma CategoryNarrative; devuelve undefined si la síntesis vino mal formada para que el llamador caiga al fallback local. */
function toCategoryNarrative(value: unknown): CategoryNarrative | undefined {
  if (!isRecord(value)) {
    return undefined;
  }

  const rawSources = Array.isArray(value.sources) ? value.sources : [];
  const { sources, idMapping } = dedupeNarrativeSources(
    rawSources.map(toNarrativeSource).filter((source): source is NarrativeSource => source !== null),
  );

  const rawBlocks = Array.isArray(value.blocks) ? value.blocks : [];
  const blocks = rawBlocks
    .map(toNarrativeBlock)
    .filter((block): block is NarrativeBlockData => block !== null)
    .map((block) => remapNarrativeBlockSourceIds(block, idMapping));

  if (blocks.length === 0) {
    return undefined;
  }

  return { blocks, sources };
}

/** Solo para PlazoItem; se preserva sin aplanar para que la timeline use fechas literales sin inventar. */
function toPlazoRawFields(item: Record<string, unknown>): PlazoRawFields | undefined {
  if (!("fecha" in item) && !("expresion_relativa" in item) && !("texto_original" in item)) {
    return undefined;
  }
  return {
    fecha: item.fecha == null ? null : String(item.fecha),
    hora: item.hora == null ? null : String(item.hora),
    expresion_relativa: item.expresion_relativa == null ? null : String(item.expresion_relativa),
    texto_original: item.texto_original == null ? null : String(item.texto_original),
    lugar: item.lugar == null ? null : String(item.lugar),
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

/** El estado agregado de cada categoría viaja en una clave hermana (`${categoryId}_extraction_status`). */
const BACKEND_STATUS_KEY: Record<CategoryId, string> = {
  plazos_clave: "plazos_clave_extraction_status",
  garantias: "garantias_extraction_status",
  causales_rechazo: "causales_rechazo_extraction_status",
  objeto_alcance: "objeto_alcance_extraction_status",
  requisitos_admisibilidad: "requisitos_admisibilidad_extraction_status",
  criterios_evaluacion: "criterios_evaluacion_extraction_status",
  anexos_obligatorios: "anexos_obligatorios_extraction_status",
  datos_procedimiento: "datos_procedimiento_extraction_status",
  riesgos: "riesgos_extraction_status",
};

const FIELD_LABELS: Record<string, string> = {
  presentacion_ofertas: "Presentación de ofertas",
  apertura: "Apertura de ofertas",
  consultas: "Consultas",
  respuesta_consultas: "Respuesta a consultas",
  visita_obra: "Visita a obra",
  mantenimiento_oferta: "Mantenimiento de oferta",
  tiempo_entrega: "Tiempo de entrega",
  forma_pago: "Forma de Pago",
  moneda: "Licitación en pesos o dólares",
  tipo_cambio: "Tipo de cambio",
  garantias_cauciones: "Garantías o cauciones",
  multas_penalidades: "Multas y penalidades",
  anticipo_financiero: "Anticipo financiero",
  requisitos_tecnicos_excluyentes: "Requisitos técnicos o certificaciones excluyentes",
  responsabilidad_costos_logisticos: "Responsabilidad por costos logísticos o de instalación",
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
  organismo_convocante: "Organismo convocante",
  expediente: "Expediente",
  numero_procedimiento: "Procedimiento",
  tipo_procedimiento: "Tipo de procedimiento",
  jurisdiccion: "Jurisdicción",
  denominacion: "Denominación",
  otro: "Otro",
  otra: "Otra",
  // TipoRiesgo
  descalificacion: "Descalificación",
  penalizacion: "Penalización",
  legal: "Legal",
  operativo: "Operativo",
  financiero: "Financiero",
  // SubtipoRiesgo
  ejecucion: "Ejecución",
  incumplimiento: "Incumplimiento",
  plazos: "Plazos",
  economico: "Económico",
  tecnico: "Técnico",
  legal_contractual: "Legal/Contractual",
  comercial: "Comercial",
  otro_explicito: "Otro",
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
  const raw = toPlazoRawFields(value);
  const fieldValue = backendItemValue(value);
  const hasEvidence = refsRaw.some((ref) => {
    if (!isRecord(ref)) {
      return false;
    }
    const citation = String(ref.citation ?? "").trim();
    return citation.length > 0;
  });

  const shouldOverrideNotFound = (status === "not_found" || status === "failed") && (fieldValue != null || hasEvidence);
  const fieldState = shouldOverrideNotFound ? "extraido" : (STATE_BY_STATUS[status] ?? "extraido");

  // PlazoItem usa `referencia` (texto libre del LLM) en vez de `tipo`; el resto de las categorías sí usan `tipo`.
  const referencia = value.referencia == null ? "" : String(value.referencia).trim();

  // Para RiesgoItem, incluir subtipo en el field_name para permitir agrupamiento
  const tipo = String(value.tipo ?? "");
  const subtipo = value.subtipo ? String(value.subtipo) : null;
  const fieldName = referencia
    ? referencia
    : subtipo
      ? `${humanizeTipo(tipo)} (${humanizeTipo(subtipo)})`
      : humanizeTipo(tipo);

  return {
    field_name: fieldName,
    field_value: fieldValue,
    field_state: fieldState,
    confidence: Number(value.confidence ?? 0),
    citations: refsRaw.filter(isRecord).map((ref) => ({
      text: String(ref.citation ?? ""),
      page: Number(ref.page_number ?? 0),
      document_id: String(ref.document_id ?? ""),
      document_name: toDocumentName(ref),
    })),
    ...(raw ? { raw } : {}),
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
  narrativeFromSibling?: unknown,
  categoryConfidenceFromSibling?: unknown,
): CategoryData {
  const items = rawItems.map(fromBackendItem).filter((item): item is FieldItem => item !== null);

  let confidence = Number(categoryConfidenceFromSibling ?? 0);
  if (!Number.isFinite(confidence) || confidence <= 0) {
    const withConfidence = items.filter((item) => Number.isFinite(item.confidence) && item.confidence > 0);
    confidence =
      withConfidence.length > 0
        ? withConfidence.reduce((total, item) => total + item.confidence, 0) / withConfidence.length
        : 0;
  }

  const sourceReferencesSeen = new Set<string>();
  const sourceReferences: SourceReference[] = [];
  for (const item of items) {
    for (const citation of item.citations) {
      const key = `${citation.document_id}|${citation.page}|${citation.text.trim().toLowerCase()}`;
      if (sourceReferencesSeen.has(key)) {
        continue;
      }
      sourceReferencesSeen.add(key);
      sourceReferences.push({ page: citation.page, document_id: citation.document_id, text_snippet: citation.text });
    }
  }

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
    narrative: toCategoryNarrative(narrativeFromSibling),
  };
}

/** Lista completa de CategoryId (a diferencia de CATEGORY_ORDER, que excluye datos_procedimiento) para que el header del análisis no quede vacío. */
const NORMALIZE_CATEGORY_IDS: Array<CategoryId | "preview_criterios"> = [
  "preview_criterios",
  ...CATEGORY_ORDER,
  "datos_procedimiento",
];

function normalizeCategories(extractedData: unknown): Record<CategoryId, CategoryData> & {
  preview_criterios?: CategoryData;
} {
  const result = NORMALIZE_CATEGORY_IDS.reduce<
    Record<CategoryId, CategoryData> & { preview_criterios?: CategoryData }
  >((acc, categoryId) => {
    acc[categoryId] = emptyCategoryData();
    return acc;
  }, {} as Record<CategoryId, CategoryData> & { preview_criterios?: CategoryData });

  if (!isRecord(extractedData)) {
    return result;
  }

  const getStatusValue = (categoryId: CategoryId | "preview_criterios"): unknown =>
    categoryId === "preview_criterios"
      ? extractedData.preview_criterios_extraction_status
      : extractedData[BACKEND_STATUS_KEY[categoryId]];

  for (const categoryId of NORMALIZE_CATEGORY_IDS) {
    const rawCategory = extractedData[categoryId];

    // El backend siempre emite: categoría=array de ítems, estado en clave hermana, narrativa en `${categoryId}_narrative`.
    if (!Array.isArray(rawCategory)) {
      continue;
    }

    result[categoryId] = fromBackendArray(
      rawCategory,
      getStatusValue(categoryId),
      extractedData[`${categoryId}_narrative`],
      extractedData[`${categoryId}_confidence`],
    );
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
    tracking: null,
  };
}

export async function getAnalysisById(analysisId: string): Promise<AnalysisDetail> {
  try {
    const response = await apiClient.get<AnalysisDetail>(`/analyses/${analysisId}`);
    const payload = response.data;
    currentDocumentNameById = buildDocumentNameById(payload.documents);
    const normalizedVersions = Array.isArray(payload.versions)
      ? payload.versions.map((version) => ({
          ...version,
          extracted_data: normalizeCategories(version?.extracted_data),
        }))
      : undefined;
    const normalized = {
      ...payload,
      current_version: {
        ...payload.current_version,
        extracted_data: normalizeCategories(payload.current_version?.extracted_data),
      },
      versions: normalizedVersions,
    };
    currentDocumentNameById = new Map();
    return normalized;
  } catch (error) {
    currentDocumentNameById = new Map();
    if (error instanceof AxiosError && error.response?.status === 404) {
      const statusResponse = await apiClient.get<AnalysisStatusResponse>(`/analyses/${analysisId}/status`);
      return mapStatusToDetail(analysisId, statusResponse.data);
    }
    throw error;
  }
}
