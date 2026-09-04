import { NarrativeBlocks } from "./components/NarrativeBlocks";
import type { AnalysisDetail, CategoryData, CategoryNarrative, Citation, NarrativeSource } from "./types";
import { buildNarrativeBlocks, mergeCategoryNarratives } from "./utils/narrativeSynthesis";

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
  if (!category || category.items.length === 0) {
    return null;
  }
  return category.narrative ?? buildNarrativeBlocks(category, fallbackCategoryId, options);
}

export function PreviewTab({ analysis, onViewSource }: PreviewTabProps) {
  const extractedData = analysis.current_version.extracted_data;
  const objetoAlcance = extractedData.objeto_alcance;
  const previewCriterios = normalizePreviewCategory(extractedData.preview_criterios);
  const hasPreviewCategory = previewCriterios !== undefined;

  const objetoNarrative = categoryNarrativeOrFallback(objetoAlcance, "objeto_alcance");
  // "criterios_evaluacion" es un placeholder: preview_criterios no es un
  // CategoryId real (no tiene su propia sección en Categorías), pero
  // buildNarrativeBlocks necesita alguno para el texto de fallback y la
  // decisión lista-vs-párrafo. No afecta el resultado salvo cuando faltan
  // datos y el backend tampoco mandó narrative.
  const previewNarrative = normalizePreviewNarrative(
    categoryNarrativeOrFallback(previewCriterios, "criterios_evaluacion", {
    forceList: true,
    includeNotFoundItems: true,
    }),
  );

  const unifiedNarrative =
    objetoNarrative || previewNarrative
      ? mergeCategoryNarratives([objetoNarrative, previewNarrative].filter((n): n is CategoryNarrative => n !== null))
      : null;

  return (
    <section data-testid="preview-tab-content">
      {unifiedNarrative ? (
        <NarrativeBlocks narrative={unifiedNarrative} onViewSource={onViewSource} emphasizeLeadingLabel />
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

      {unifiedNarrative ? (
        <p className="mt-3 text-xs text-gray-500" data-testid="preview-tab-categories-hint">
          Este preview es un resumen. Podés ver el detalle completo de requisitos de admisibilidad y garantías,
          con todas sus fuentes, en la sección Categorías.
        </p>
      ) : null}
    </section>
  );
}
