import { ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";

import { PreviewCriterionCard } from "./components/PreviewCriterionCard";
import type { AnalysisDetail, CategoryData, CategoryNarrative, Citation, NarrativeSource } from "./types";
import { filterVerifiedSources, collectReferencedSourceIds, resolveSourceIdsToSources } from "./utils/resolveNarrativeSources";
import { normalizePreviewSummary } from "./utils/normalizePreviewSummary";
import { splitLabelAndValue } from "./utils/splitLabelAndValue";
import { buildNarrativeBlocks } from "./utils/narrativeSynthesis";

interface PreviewTabProps {
  analysis: AnalysisDetail;
  onViewSource?: (payload: { citation: Citation; citations: Citation[]; sources: NarrativeSource[] }) => void;
}

const PREVIEW_TITLES = [
  "Mantenimiento de oferta",
  "Tiempo de entrega",
  "Forma de pago",
  "Licitación en pesos o dólares",
  "Tipo de cambio",
  "Garantías o cauciones",
  "Multas o penalidades",
  "Anticipo financiero requerido",
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
  moneda: "Licitación en pesos o dólares",
  "moneda de cotizacion": "Licitación en pesos o dólares",
  "moneda de cotización": "Licitación en pesos o dólares",
  "licitacion en pesos o dolares": "Licitación en pesos o dólares",
  "licitación en pesos o dólares": "Licitación en pesos o dólares",
  "tipo de cambio": "Tipo de cambio",
  garantias: "Garantías o cauciones",
  "garantías": "Garantías o cauciones",
  "garantias y cauciones": "Garantías o cauciones",
  "garantías y cauciones": "Garantías o cauciones",
  "garantias o cauciones": "Garantías o cauciones",
  "garantías o cauciones": "Garantías o cauciones",
  "multas y penalidades": "Multas o penalidades",
  "multas o penalidades": "Multas o penalidades",
  "anticipo financiero": "Anticipo financiero requerido",
  "anticipo financiero requerido": "Anticipo financiero requerido",
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

export function PreviewTab({ analysis, onViewSource }: PreviewTabProps) {
  const [showObjectSources, setShowObjectSources] = useState(false);

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
              className="relative mt-3 overflow-hidden rounded-xl border border-white/50 bg-white/35 p-4 pb-12 shadow-md backdrop-blur-md sm:p-5 sm:pb-12"
              data-testid="preview-object-card"
            >
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-cedia-primary">Objeto y Alcance</h3>
                  <p className="mt-2 whitespace-pre-line break-words text-sm leading-relaxed text-gray-800" data-testid="preview-object-text">
                    {objectDetailText}
                  </p>
                </div>
              </div>

              {showObjectSources ? (
                <div id="preview-object-sources" className="mt-3 rounded-md border border-white/60 bg-white/75 p-2 backdrop-blur" data-testid="preview-object-sources-panel">
                  {objectSources.length > 0 ? (
                    <ul className="space-y-2" data-testid="preview-object-sources-list">
                      {objectSources.map((source) => (
                        <li key={source.id}>
                          <button
                            type="button"
                            className="w-full rounded border border-gray-200 px-2 py-1 text-left text-xs text-cedia-primary hover:border-cedia-primary"
                            onClick={() => handleViewObjectSource(source)}
                          >
                            <span className="font-semibold">{source.document_name}</span>
                            <span>{` · pág. ${source.page}`}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-gray-600">Sin fuentes verificables para Objeto y Alcance.</p>
                  )}
                </div>
              ) : null}

              <button
                type="button"
                className="absolute bottom-2 right-2 inline-flex h-7 w-7 items-center justify-center rounded-full border border-cedia-primary/40 bg-white/75 text-cedia-primary transition-colors hover:border-cedia-primary hover:bg-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                aria-expanded={showObjectSources}
                aria-controls="preview-object-sources"
                aria-label={showObjectSources ? "Ocultar fuentes" : "Mostrar fuentes"}
                title={showObjectSources ? "Ocultar fuentes" : "Mostrar fuentes"}
                onClick={() => setShowObjectSources((value) => !value)}
                data-testid="preview-object-sources-toggle"
              >
                {showObjectSources ? <ChevronUp className="h-4 w-4" aria-hidden="true" /> : <ChevronDown className="h-4 w-4" aria-hidden="true" />}
              </button>
            </article>
          ) : null}

          {previewBullets.length > 0 ? (
            <div className="mt-3 flex w-full flex-wrap gap-2 overflow-x-hidden" data-testid="preview-criteria-cards">
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
                    contentId={`preview-criterion-content-${index}`}
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
    </section>
  );
}
