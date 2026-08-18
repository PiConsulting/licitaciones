import { AxiosError } from "axios";

import apiClient from "../../api/client";
import { dedupeNarrativeSources, remapSourceIds } from "../../features/analysis-detail/utils/dedupeCitations";
import {
  type AnalysisDetail,
  type CategoryData,
  type CategoryId,
  type CategoryNarrative,
  type CategoryQuality,
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isGenericDocumentLabel(value: string): boolean {
  return value.trim().toLocaleLowerCase("es") === "documento";
}

function pickDocumentName(record: Record<string, unknown>): string {
  const candidates = [
    record.document_name,
    record.documentName,
    record.filename,
    record.document_filename,
    record.source_filename,
    record.file_name,
    record.fileName,
  ];

  for (const candidate of candidates) {
    const text = String(candidate ?? "").trim();
    if (text !== "") {
      return text;
    }
  }

  return "Documento";
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

/** Las coordenadas de resaltado que calculó el backend, tal cual vienen.
 *
 * FIX (2026-08-14): este mapper NO copiaba `highlight_regions`, y es el único
 * constructor de `NarrativeSource` en todo el frontend. O sea que
 * `getCombinedHighlightRegions()` devolvía SIEMPRE `[]`, `useCoordinateHighlight`
 * era SIEMPRE `false`, y el visor caía SIEMPRE al resaltado heurístico por
 * texto. El camino de coordenadas era código muerto en producción.
 *
 * Eso explica por qué varias correcciones del cálculo de coordenadas en el
 * backend no cambiaron nada de lo que se veía: los números llegaban bien hasta
 * el borde de la API y se descartaban acá. Los tests no lo detectaban porque
 * mockean la respuesta ya mapeada o construyen las regiones a mano.
 */
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

  const page = Number(value.page_number ?? value.page ?? 0);
  const text = String(value.citation ?? value.text ?? "");

  return {
    id: Number(value.id ?? 0),
    document_id: String(value.document_id ?? ""),
    document_name: pickDocumentName(value),
    page,
    text,
    unverified: Boolean(value.unverified),
    highlight_regions: toHighlightRegions(value.highlight_regions),
  };
}

/** Convierte un bloque crudo del backend (o de un narrative mal formado) a la
 * forma tipada. Devuelve null ante cualquier bloque irreconocible en vez de
 * lanzar — un bloque malformado nunca puede tumbar el resto de la respuesta. */
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
        confidence_level: toConfidenceLevel(item.confidence_level),
        source_ids: toSourceIds(item.source_ids),
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

/** Remapea los `source_ids` de un bloque ya tipado con el mapping que dejó la
 * deduplicación de fuentes, para que ningún bloque quede apuntando a un id
 * que la fusión de sources descartó. */
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

/** Arma la CategoryNarrative del backend en la forma tipada del frontend. Es
 * defensivo a propósito: si la síntesis vino mal formada o vacía, devuelve
 * undefined y el llamador cae al fallback local en vez de romper la vista. */
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

/** Solo presente en ítems con forma de PlazoItem (mismo chequeo que usa
 * `backendItemValue` para reconocerlos). Se preserva sin aplanar para que la
 * timeline pueda ubicar fechas literales sin inventar ninguna. */
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
        document_name: pickDocumentName(citation),
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
 * 
 * FIX: Migrado a campos canónicos (#4 auditoría RAG)
 * - anexos_obligatorios_extraction_status (NO anexos_extraction_status)
 * - criterios_evaluacion_extraction_status (NO criterios_extraction_status)
 * 
 * Los campos legacy siguen funcionando hasta Q2 2027, pero se recomienda
 * usar los canónicos para evitar problemas futuros.
 */
const BACKEND_STATUS_KEY: Record<CategoryId, string> = {
  plazos_clave: "plazos_clave_extraction_status",
  garantias: "garantias_extraction_status",
  causales_rechazo: "causales_extraction_status",
  objeto_alcance: "objeto_alcance_extraction_status",
  requisitos_admisibilidad: "requisitos_admisibilidad_extraction_status",
  criterios_evaluacion: "criterios_evaluacion_extraction_status",
  anexos_obligatorios: "anexos_obligatorios_extraction_status",
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
  organismo_convocante: "Organismo convocante",
  expediente: "Expediente",
  numero_procedimiento: "Procedimiento",
  tipo_procedimiento: "Tipo de procedimiento",
  jurisdiccion: "Jurisdicción",
  denominacion: "Denominación",
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

  return {
    field_name: humanizeTipo(String(value.tipo ?? "")),
    field_value: fieldValue,
    field_state: fieldState,
    confidence: Number(value.confidence ?? 0),
    citations: refsRaw.filter(isRecord).map((ref) => ({
      text: String(ref.citation ?? ""),
      page: Number(ref.page_number ?? 0),
      document_id: String(ref.document_id ?? ""),
      document_name: pickDocumentName(ref),
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

function hasClickableEvidence(items: FieldItem[]): boolean {
  return items.some((item) =>
    item.citations.some(
      (citation) => citation.document_id.trim() !== "" && citation.page > 0 && citation.text.trim() !== "",
    ),
  );
}

/** Construye CategoryData a partir del array de ítems que emite el backend. */
function fromBackendArray(
  rawItems: unknown[],
  statusFromSibling: unknown,
  narrativeFromSibling?: unknown,
  categoryConfidenceFromSibling?: unknown,
): CategoryData {
  const items = rawItems.map(fromBackendItem).filter((item): item is FieldItem => item !== null);

  // Usar confidence de categoría del backend si existe; si no, fallback a promedio.
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

/**
 * `CATEGORY_ORDER` es solo el orden de las tarjetas de categoría visibles en la
 * UI y excluye a propósito `datos_procedimiento` (no tiene tarjeta propia, ver
 * `categoryIcons.tsx`). Para normalizar datos del backend hace falta la lista
 * completa de `CategoryId`, si no `datos_procedimiento` nunca se puebla y el
 * organismo/expediente del header del análisis quedan siempre vacíos.
 */
const NORMALIZE_CATEGORY_IDS: CategoryId[] = [...CATEGORY_ORDER, "datos_procedimiento"];

/** Los contadores de calidad que emite `merge_node` por categoría (ATR-03). */
function toCategoryQuality(value: unknown): CategoryQuality | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const quality: CategoryQuality = {};
  for (const key of [
    "descartados_sin_evidencia",
    "descartados_por_formato",
    "con_evidencia_rescatada",
    "conservados",
  ] as const) {
    const raw = Number(value[key]);
    if (Number.isFinite(raw) && raw > 0) {
      quality[key] = raw;
    }
  }
  return Object.keys(quality).length > 0 ? quality : undefined;
}

function normalizeCategories(extractedData: unknown): Record<CategoryId, CategoryData> {
  const result = NORMALIZE_CATEGORY_IDS.reduce<Record<CategoryId, CategoryData>>((acc, categoryId) => {
    acc[categoryId] = emptyCategoryData();
    return acc;
  }, {} as Record<CategoryId, CategoryData>);

  if (!isRecord(extractedData)) {
    return result;
  }

  // FIX: Mapeo legacy solo para retrocompatibilidad (#4 auditoría RAG)
  // El backend actual envía ambos nombres (canónico + legacy), pero versiones
  // antiguas o análisis legacy pueden tener solo los nombres viejos.
  // Este fallback se puede eliminar después de Q2 2027 cuando se deprecien
  // completamente los campos legacy del backend.
  const legacyToUiMap: Partial<Record<CategoryId, string[]>> = {
    plazos_clave: ["plazos"],
    requisitos_admisibilidad: ["documentos_requeridos", "restricciones_participacion"],
    datos_procedimiento: ["cronograma_proceso", "estimacion_presupuesto"],
  };

  const calidadPorCategoria = isRecord(extractedData.calidad_por_categoria)
    ? (extractedData.calidad_por_categoria as Record<string, unknown>)
    : {};

  for (const categoryId of NORMALIZE_CATEGORY_IDS) {
    let rawCategory = extractedData[categoryId];

    // Forma actual del backend: la categoría es un array de ítems, el estado
    // agregado viaja en una clave hermana, y la narrativa de síntesis (cuando
    // corrió) en `${categoryId}_narrative`.
    if (Array.isArray(rawCategory)) {
      result[categoryId] = fromBackendArray(
        rawCategory,
        extractedData[BACKEND_STATUS_KEY[categoryId]],
        extractedData[`${categoryId}_narrative`],
        extractedData[`${categoryId}_confidence`],
      );
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
          extractedData[`${categoryId}_narrative`],
          extractedData[`${categoryId}_confidence`],
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
    const extractionStatus = [
      "success",
      "partial",
      "failed",
      "not_found",
      "not_applicable",
      "not_analyzed",
    ].includes(statusValue)
      ? (statusValue as CategoryData["extraction_status"])
      : "partial";

    result[categoryId] = {
      items,
      confidence: Number(rawCategory.confidence ?? 0),
      source_references: refs,
      extraction_status: extractionStatus,
      summary: String(rawCategory.summary ?? "Sin resumen disponible."),
      is_reviewed: Boolean(rawCategory.is_reviewed) && hasClickableEvidence(items),
      narrative: toCategoryNarrative(rawCategory.narrative),
      quality: toCategoryQuality(calidadPorCategoria[categoryId]),
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

function hydrateCategoryDocumentNames(
  category: CategoryData,
  documentsById: Map<string, string>,
): CategoryData {
  const items = category.items.map((item) => ({
    ...item,
    citations: item.citations.map((citation) => {
      const mappedName = documentsById.get(citation.document_id);
      const needsHydration = citation.document_name.trim() === "" || isGenericDocumentLabel(citation.document_name);
      return {
        ...citation,
        document_name: needsHydration ? (mappedName ?? citation.document_name) : citation.document_name,
      };
    }),
  }));

  const narrative = category.narrative
    ? {
        ...category.narrative,
        sources: category.narrative.sources.map((source) => {
          const mappedName = documentsById.get(source.document_id);
          const needsHydration = source.document_name.trim() === "" || isGenericDocumentLabel(source.document_name);
          return {
            ...source,
            document_name: needsHydration ? (mappedName ?? source.document_name) : source.document_name,
          };
        }),
      }
    : category.narrative;

  return {
    ...category,
    items,
    narrative,
  };
}

function hydrateAnalysisDocumentNames(payload: AnalysisDetail): AnalysisDetail {
  const documentsById = new Map(payload.documents.map((document) => [document.id, document.filename]));
  const extracted = payload.current_version?.extracted_data;
  if (!extracted || documentsById.size === 0) {
    return payload;
  }

  const hydrated = Object.fromEntries(
    Object.entries(extracted).map(([categoryId, category]) => [
      categoryId,
      hydrateCategoryDocumentNames(category, documentsById),
    ]),
  ) as Record<CategoryId, CategoryData>;

  return {
    ...payload,
    current_version: {
      ...payload.current_version,
      extracted_data: hydrated,
    },
  };
}

export async function getAnalysisById(analysisId: string): Promise<AnalysisDetail> {
  try {
    const response = await apiClient.get<AnalysisDetail>(`/analyses/${analysisId}`);
    const payload = response.data;
    const normalized = {
      ...payload,
      current_version: {
        ...payload.current_version,
        extracted_data: normalizeCategories(payload.current_version?.extracted_data),
      },
    };
    return hydrateAnalysisDocumentNames(normalized);
  } catch (error) {
    if (error instanceof AxiosError && error.response?.status === 404) {
      const statusResponse = await apiClient.get<AnalysisStatusResponse>(`/analyses/${analysisId}/status`);
      return mapStatusToDetail(analysisId, statusResponse.data);
    }
    throw error;
  }
}
