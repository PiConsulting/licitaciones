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

function normalizeCategories(extractedData: unknown): Record<CategoryId, CategoryData> {
  const result = CATEGORY_ORDER.reduce<Record<CategoryId, CategoryData>>((acc, categoryId) => {
    acc[categoryId] = emptyCategoryData();
    return acc;
  }, {} as Record<CategoryId, CategoryData>);

  if (!isRecord(extractedData)) {
    return result;
  }

  for (const categoryId of CATEGORY_ORDER) {
    const rawCategory = extractedData[categoryId];
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
    const extractionStatus = ["success", "partial", "failed"].includes(statusValue)
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
