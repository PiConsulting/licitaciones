import { Ban, Eye } from "lucide-react";

import { BusinessDecisionPanel } from "./components/BusinessDecisionPanel";
import { PreviewCriterionCard } from "./components/PreviewCriterionCard";
import type {
  AnalysisDetail,
  CategoriesDecision,
  CategoryData,
  CategoryNarrative,
  Citation,
  NarrativeSource,
} from "./types";
import { filterVerifiedSources, collectReferencedSourceIds, resolveSourceIdsToSources } from "./utils/resolveNarrativeSources";
import { normalizePreviewSummary } from "./utils/normalizePreviewSummary";
import { resolveBusinessStatus } from "./utils/businessStatus";
import { splitLabelAndValue } from "./utils/splitLabelAndValue";
import { buildNarrativeBlocks } from "./utils/narrativeSynthesis";

interface PreviewTabProps {
  analysis: AnalysisDetail;
  onViewSource?: (payload: { citation: Citation; citations: Citation[]; sources: NarrativeSource[] }) => void;
  decisionLoading?: boolean;
  onApproveDecision?: () => Promise<void> | void;
  onRejectDecision?: (note: string) => Promise<void> | void;
  categoriesDecision?: CategoriesDecision | null;
  categoriesDecisionByName?: string | null;
  categoriesDecisionAt?: string | null;
}

const PREVIEW_TITLES = [
  "Mantenimiento de oferta",
  "Tiempo de entrega",
  "Forma de pago",
  "Moneda",
  "Tipo de cambio",
  "Garantías o cauciones",
  "Multas o penalidades",
  "Anticipo financiero",
  "Requisitos técnicos o certificaciones excluyentes",
  "Responsabilidad por costos logísticos o de instalación",
] as const;

const PREVIEW_ALIASES: Record<string, (typeof PREVIEW_TITLES)[number] | null> = {
  "mantenimiento de oferta": "Mantenimiento de oferta",
  "mantenimiento de la oferta": "Mantenimiento de oferta",
  "tiempo de entrega": "Tiempo de entrega",
  "plazo y lugar de entrega": "Tiempo de entrega",
  "plazo de entrega": "Tiempo de entrega",
  "forma de pago": "Forma de pago",
  moneda: "Moneda",
  "moneda de cotizacion": "Moneda",
  "moneda de cotización": "Moneda",
  "licitacion en pesos o dolares": "Moneda",
  "licitación en pesos o dólares": "Moneda",
  "tipo de cambio": "Tipo de cambio",
  garantias: "Garantías o cauciones",
  "garantías": "Garantías o cauciones",
  "garantias y cauciones": "Garantías o cauciones",
  "garantías y cauciones": "Garantías o cauciones",
  "garantias o cauciones": "Garantías o cauciones",
  "garantías o cauciones": "Garantías o cauciones",
  "multas y penalidades": "Multas o penalidades",
  "multas o penalidades": "Multas o penalidades",
  "anticipo financiero": "Anticipo financiero",
  "anticipo financiero requerido": "Anticipo financiero",
  "requisitos tecnicos excluyentes": "Requisitos técnicos o certificaciones excluyentes",
  "requisitos técnicos excluyentes": "Requisitos técnicos o certificaciones excluyentes",
  "requisitos tecnicos o certificaciones excluyentes": "Requisitos técnicos o certificaciones excluyentes",
  "requisitos técnicos o certificaciones excluyentes": "Requisitos técnicos o certificaciones excluyentes",
  "responsabilidad por costos logisticos": "Responsabilidad por costos logísticos o de instalación",
  "responsabilidad por costos logísticos": "Responsabilidad por costos logísticos o de instalación",
  "responsabilidad por costos logisticos o de instalacion": "Responsabilidad por costos logísticos o de instalación",
  "responsabilidad por costos logísticos o de instalación": "Responsabilidad por costos logísticos o de instalación",
  "costos logisticos": "Responsabilidad por costos logísticos o de instalación",
  "costos logísticos": "Responsabilidad por costos logísticos o de instalación",
};

const PREVIEW_INDEX = new Map<string, number>(PREVIEW_TITLES.map((title, index) => [title, index]));

function normalizeLabel(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function canonicalPreviewTitle(label: string): (typeof PREVIEW_TITLES)[number] | null | undefined {
  const key = normalizeLabel(label);
  return PREVIEW_ALIASES[key];
}

function normalizePreviewCategory(category: CategoryData | undefined): CategoryData | undefined {
  if (!category) {
    return category;
  }

  const orderedItems = category.items
    .map((item, index) => {
      const canonical = canonicalPreviewTitle(item.field_name);
      if (canonical === null) {
        return null;
      }
      const fieldName = canonical ?? item.field_name;
      const order = PREVIEW_INDEX.get(fieldName) ?? Number.MAX_SAFE_INTEGER;
      return {
        ...item,
        field_name: fieldName,
        _previewOrder: order,
        _originalIndex: index,
      };
    })
    .filter(
      (
        item,
      ): item is CategoryData["items"][number] & {
        _previewOrder: number;
        _originalIndex: number;
      } => item !== null,
    )
    .sort((a, b) => (a._previewOrder === b._previewOrder ? a._originalIndex - b._originalIndex : a._previewOrder - b._previewOrder))
    .map(({ _previewOrder: _, _originalIndex: __, ...item }) => item);

  return {
    ...category,
    items: orderedItems,
  };
}

function normalizePreviewNarrative(narrative: CategoryNarrative | null): CategoryNarrative | null {
  if (!narrative) {
    return null;
  }

  const normalizedBlocks = narrative.blocks.map((block) => {
    if (block.type !== "bullet_list") {
      return block;
    }

    const transformed = block.items
      .map((item, index) => {
        const [rawLabel, ...rest] = item.text.split(":");
        const canonical = canonicalPreviewTitle(rawLabel ?? "");
        if (canonical === null) {
          return null;
        }
        if (!canonical) {
          return {
            ...item,
            _previewOrder: Number.MAX_SAFE_INTEGER,
            _originalIndex: index,
          };
        }
        const restText = rest.join(":").trim();
        const text = restText ? `${canonical}: ${restText}` : canonical;
        return {
          ...item,
          text,
          _previewOrder: PREVIEW_INDEX.get(canonical) ?? Number.MAX_SAFE_INTEGER,
          _originalIndex: index,
        };
      })
      .filter(
        (
          item,
        ): item is typeof block.items[number] & {
          _previewOrder: number;
          _originalIndex: number;
        } => item !== null,
      )
      .sort((a, b) => (a._previewOrder === b._previewOrder ? a._originalIndex - b._originalIndex : a._previewOrder - b._previewOrder))
      .map(({ _previewOrder: _, _originalIndex: __, ...item }) => item);

    return {
      ...block,
      items: transformed,
    };
  });

  return {
    ...narrative,
    blocks: normalizedBlocks,
  };
}

/**
 * Narrativa de una categoría para el preview: usa la síntesis real del
 * backend (`category.narrative`, el mismo texto corto que se ve en
 * Categorías) cuando está disponible, y sólo recurre al armado local de
 * `buildNarrativeBlocks` si el backend todavía no la generó. Antes esta vista
 * reconstruía todo desde los `items` crudos, lo que producía un texto de
 * "Objeto" mucho más largo que el de Categorías -- dos representaciones
 * distintas del mismo dato. Ahora es la misma.
 *
 * Devuelve `null` cuando la categoría no tiene ítems, para no mostrar el
 * párrafo genérico de "no se encontró información" de `buildNarrativeBlocks`
 * dentro de una vista que ya avisa por separado cuando no hay nada.
 */
function categoryNarrativeOrFallback(
  category: CategoryData | undefined,
  fallbackCategoryId: Parameters<typeof buildNarrativeBlocks>[1],
  options?: Parameters<typeof buildNarrativeBlocks>[2],
): CategoryNarrative | null {
  if (!category) {
    return null;
  }
  if (category.narrative) {
    return category.narrative;
  }
  if (category.items.length === 0) {
    return null;
  }
  return buildNarrativeBlocks(category, fallbackCategoryId, options);
}

function formatDecisionDate(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function PreviewTab({
  analysis,
  onViewSource,
  decisionLoading = false,
  onApproveDecision,
  onRejectDecision,
  categoriesDecision = null,
  categoriesDecisionByName,
  categoriesDecisionAt,
}: PreviewTabProps) {
  const isPendingDecision = resolveBusinessStatus(analysis.business_status) === "pendiente_decision";
  const extractedData = analysis.current_version.extracted_data;
  const objetoAlcance = extractedData.objeto_alcance;
  const previewCriterios = normalizePreviewCategory(extractedData.preview_criterios);
  const hasPreviewCategory = previewCriterios !== undefined;

  const objetoNarrative = categoryNarrativeOrFallback(objetoAlcance, "objeto_alcance");
  // "criterios_evaluacion" es un placeholder: preview_criterios no es un CategoryId real, pero buildNarrativeBlocks necesita alguno para el fallback.
  const previewNarrative = normalizePreviewNarrative(
    categoryNarrativeOrFallback(previewCriterios, "criterios_evaluacion", {
      forceList: true,
      includeNotFoundItems: true,
    }),
  );

  const previewBullets = previewNarrative?.blocks.flatMap((block) => (block.type === "bullet_list" ? block.items : [])) ?? [];
  const previewReferencedIds = collectReferencedSourceIds(previewNarrative?.blocks ?? []);
  const previewSourceById = new Map(
    filterVerifiedSources(previewNarrative?.sources ?? [])
      .filter((source) => previewReferencedIds.has(source.id))
      .map((source) => [source.id, source]),
  );
  const objectReferencedIds = collectReferencedSourceIds(objetoNarrative?.blocks ?? []);
  const objectSources = filterVerifiedSources(objetoNarrative?.sources ?? []).filter((source) =>
    objectReferencedIds.has(source.id),
  );
  const objectDetailText =
    objetoNarrative?.blocks
      .map((block) => {
        if (block.type === "paragraph") {
          return block.text;
        }
        if (block.type === "bullet_list") {
          return block.items.map((item) => item.text).join("\n");
        }
        return block.rows.map((row) => row.cells.join(" · ")).join("\n");
      })
      .filter(Boolean)
      .join("\n\n") ?? "";

  const handleViewObjectSource = (selectedSource: NarrativeSource) => {
    if (!onViewSource) {
      return;
    }
    const citations = objectSources.map((source) => ({
      text: source.text,
      page: source.page,
      document_id: source.document_id,
      document_name: source.document_name,
    }));
    onViewSource({
      citation: {
        text: selectedSource.text,
        page: selectedSource.page,
        document_id: selectedSource.document_id,
        document_name: selectedSource.document_name,
      },
      citations,
      sources: objectSources,
    });
  };

  const hasContent = Boolean(objetoNarrative || previewBullets.length > 0);

  return (
    <section data-testid="preview-tab-content">
      {hasContent ? (
        <>
          {objetoNarrative ? (
            <article
              className="mt-3 flex flex-col gap-[10px] rounded-2xl border border-[rgba(0,60,107,.12)] bg-white px-6 py-5"
              data-testid="preview-object-card"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-[rgba(0,60,107,.68)]">Objeto y alcance</span>
                {objectSources.length > 0 ? (
                  <button
                    type="button"
                    title={`Ver fuente en el pliego (pág. ${objectSources[0].page})`}
                    aria-label={`Ver fuente en el pliego (pág. ${objectSources[0].page})`}
                    className="inline-flex h-7 items-center gap-1.5 rounded-full border border-[rgba(0,60,107,.12)] bg-white px-[10px] text-[11px] font-semibold text-[#0099DB] transition-colors hover:border-[#0099DB]"
                    onClick={() => handleViewObjectSource(objectSources[0])}
                    data-testid="preview-object-source-button"
                  >
                    <Eye className="h-[13px] w-[13px]" aria-hidden="true" />
                    {`pág. ${objectSources[0].page}`}
                  </button>
                ) : null}
              </div>

              <p className="m-0 whitespace-pre-line break-words text-[15px] leading-[1.6] text-[#003C6B]" data-testid="preview-object-text">
                {objectDetailText}
              </p>
            </article>
          ) : null}

          {previewBullets.length > 0 ? (
            <div className="mt-3 grid w-full grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-3" data-testid="preview-criteria-cards">
              {previewBullets.map((item, index) => {
                const split = splitLabelAndValue(item.text);
                const title = split?.label || PREVIEW_TITLES[index] || `Criterio ${index + 1}`;
                const summary = normalizePreviewSummary(title, item.resumen, split?.value ?? item.text);
                const sources = resolveSourceIdsToSources(item.source_ids, previewSourceById);

                return (
                  <PreviewCriterionCard
                    key={`${title}-${index}`}
                    title={title}
                    resumen={summary}
                    bulletItem={item}
                    sources={sources}
                    onViewSource={onViewSource}
                  />
                );
              })}
            </div>
          ) : null}
        </>
      ) : (
        <div
          className="rounded-md border border-gray-200 bg-gray-50 px-4 py-6 text-sm text-gray-700"
          data-testid="preview-tab-empty"
        >
          No hay contenido disponible para la vista previa de este análisis.
        </div>
      )}

      {!hasPreviewCategory ? (
        <p className="mt-3 text-xs text-gray-600" data-testid="preview-tab-legacy-note">
          Este análisis no incluye criterios de preview porque fue generado con una versión anterior del pipeline.
        </p>
      ) : null}

      {hasContent ? (
        <p className="mt-3 text-xs text-gray-500" data-testid="preview-tab-categories-hint">
          Este preview es un resumen. Podés ver el detalle completo de requisitos de admisibilidad y garantías,
          con todas sus fuentes, en la sección Categorías.
        </p>
      ) : null}

      {isPendingDecision ? (
        <div className="mt-4">
          <BusinessDecisionPanel
            loading={decisionLoading}
            onApprove={onApproveDecision ?? (() => undefined)}
            onReject={onRejectDecision ?? (() => undefined)}
          />
        </div>
      ) : null}

      {categoriesDecision === "rejected" ? (
        <div
          className="mt-4 flex items-center gap-3 rounded-2xl border border-[rgba(220,38,38,.3)] bg-[#FEF2F2] px-6 py-4 text-[#B91C1C]"
          data-testid="categories-decision-rejected-banner"
        >
          <Ban className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
          <p className="text-[13px]">
            Rechazado{categoriesDecisionByName ? ` por ${categoriesDecisionByName}` : ""}
            {formatDecisionDate(categoriesDecisionAt) ? ` el ${formatDecisionDate(categoriesDecisionAt)}` : ""}. No se
            van a analizar las categorías restantes.
          </p>
        </div>
      ) : null}
    </section>
  );
}
