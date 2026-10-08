import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Maximize2, MapPin, X } from "lucide-react";

import { getConfidenceLevel } from "../../../utils/confidence";
import { SourceEyeButton } from "./SourceEyeButton";
import { FieldBadge } from "../FieldBadge";
import type { Citation, FieldItem, NarrativeBulletItem, NarrativeSource } from "../types";

interface PlazosTimelineProps {
  items: FieldItem[];
  /** Las fuentes de la narrativa de la categoría, con sus `highlight_regions`
   * ya calculadas por el backend. Esta vista trabaja con `FieldItem` (flujo
   * legado por-campo), que no las trae; se emparejan por documento, página y
   * texto para no perder las coordenadas. */
  narrativeSources?: NarrativeSource[];
  /** Bullets de la narrativa sintetizada (título corto + detalle), en el
   * mismo orden que arma la síntesis del backend. `PlazoItem` no tiene un
   * campo de título propio -- esta vista mostraba el `field_name` genérico
   * seguido del `texto_original` completo, una oración larga sin separar
   * título de detalle (bug real, ver auditoría UI 2026-09-28). Se resuelve
   * el bullet correspondiente a cada ítem por superposición de citas, igual
   * criterio que `matchSources` ya usa para las fuentes. */
  narrativeBullets?: NarrativeBulletItem[];
  onViewSource?: (payload: { citation: Citation; citations: Citation[]; sources: NarrativeSource[] }) => void;
}

function normalizeForMatch(value: string): string {
  return value.replace(/\s+/g, " ").trim().toLowerCase();
}

/** Las `NarrativeSource` que corresponden a estas citas: mismo documento, misma
 * página, y un texto que contiene al otro (la cita del ítem y la de la fuente
 * pueden diferir en el recorte). */
function matchSources(sources: NarrativeSource[], citations: Citation[]): NarrativeSource[] {
  return sources.filter((source) =>
    citations.some((citation) => {
      if (source.document_id !== citation.document_id || source.page !== citation.page) {
        return false;
      }
      const a = normalizeForMatch(source.text);
      const b = normalizeForMatch(citation.text);
      return a !== "" && b !== "" && (a.includes(b) || b.includes(a));
    }),
  );
}

interface IndexedBullet {
  bullet: NarrativeBulletItem;
  sources: NarrativeSource[];
}

function indexBulletsBySources(bullets: NarrativeBulletItem[], sources: NarrativeSource[]): IndexedBullet[] {
  const byId = new Map(sources.map((source) => [source.id, source]));
  return bullets.map((bullet) => ({
    bullet,
    sources: bullet.source_ids.map((id) => byId.get(id)).filter((source): source is NarrativeSource => Boolean(source)),
  }));
}

/** Números + unidad de tiempo dentro del detalle (ej. "6 (seis) meses", "15
 * días", "45 días corridos") resaltados en negrita -- el dato que alguien
 * escaneando la lista busca primero, sin agregar una línea aparte. */
const DURATION_RE = /\d+\s*(?:\([^)]+\))?\s*(?:d[ií]as?|mes(?:es)?|a[ñn]os?|horas?)(?:\s+(?:corridos?|h[áa]biles?))?/gi;

function renderDetalleConNumerosEnNegrita(text: string) {
  const regex = new RegExp(DURATION_RE.source, DURATION_RE.flags);
  const nodes: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    nodes.push(
      <strong key={key++} className="font-semibold text-[rgba(0,60,107,.85)]">
        {match[0]}
      </strong>,
    );
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

/** Título corto + detalle para un `FieldItem`, resuelto contra la narrativa
 * sintetizada cuando hay un bullet cuyas fuentes se superponen con las citas
 * del ítem. Sin match (narrativa vieja, o el ítem no tiene citas todavía),
 * cae al comportamiento anterior -- nunca deja la fila sin texto. */
function resolvePlazoDisplay(item: FieldItem, indexedBullets: IndexedBullet[]): { label: string; value: string } {
  const fallbackValue = undatedValue(item) ?? "Sin detalle";
  if (item.citations.length === 0) {
    return { label: item.field_name, value: fallbackValue };
  }
  const match = indexedBullets.find(({ sources }) => matchSources(sources, item.citations).length > 0);
  const titulo = match?.bullet.titulo?.trim();
  if (match && titulo) {
    return { label: titulo, value: match.bullet.text };
  }
  return { label: item.field_name, value: fallbackValue };
}

const MIN_SPAN_DAYS = 14;
const AXIS_PADDING_X_PX = 28;
const COMPACT_HEIGHT_PX = 124;
const FULLSCREEN_HEIGHT_PX = 164;

interface DatedPlazo {
  item: FieldItem;
  date: Date;
}

function parseIsoDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) {
    return null;
  }
  const [, year, month, day] = match;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  return Number.isNaN(date.getTime()) ? null : date;
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function daysBetween(from: Date, to: Date): number {
  const MS_PER_DAY = 24 * 60 * 60 * 1000;
  return Math.round((startOfDay(to).getTime() - startOfDay(from).getTime()) / MS_PER_DAY);
}

function formatDate(date: Date): string {
  return date.toLocaleDateString("es-AR", { day: "2-digit", month: "short", year: "numeric" });
}

/** Cada plazo sin fecha fija (ej. "mantenimiento de oferta: 30 días desde la
 * apertura") es un hecho discreto e independiente de los demás -- se muestra
 * como su propia fila, no todos apretujados en un párrafo único. */
function undatedValue(item: FieldItem): string | null {
  const value = item.field_value ?? item.raw?.expresion_relativa ?? item.raw?.texto_original;
  return value ? value.trim() : null;
}

interface UndatedEntry {
  item: FieldItem;
  label: string;
  value: string;
}

interface TimelineChartProps {
  dated: DatedPlazo[];
  today: Date;
  activeIndex: number | null;
  onToggleActive: (index: number) => void;
  onViewSource: (item: FieldItem) => void;
  heightPx: number;
}

interface TimelineDayGroup {
  date: Date;
  items: FieldItem[];
}

function TimelineChart({
  dated,
  today,
  activeIndex,
  onToggleActive,
  onViewSource,
  heightPx,
}: TimelineChartProps) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [viewportWidth, setViewportWidth] = useState(0);

  useEffect(() => {
    const node = viewportRef.current;
    if (!node) {
      return;
    }

    const updateWidth = () => {
      setViewportWidth(node.clientWidth);
    };

    updateWidth();

    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", updateWidth);
      return () => window.removeEventListener("resize", updateWidth);
    }

    const observer = new ResizeObserver(updateWidth);
    observer.observe(node);

    return () => observer.disconnect();
  }, []);

  const allDates = dated.length > 0 ? dated.map((entry) => entry.date.getTime()) : [today.getTime()];
  const rangeStart = startOfDay(new Date(Math.min(...allDates, today.getTime())));
  const rangeEnd = startOfDay(new Date(Math.max(...allDates, today.getTime())));
  const spanDays = Math.max(daysBetween(rangeStart, rangeEnd), MIN_SPAN_DAYS);
  const safeViewportWidth = Math.max(viewportWidth, AXIS_PADDING_X_PX * 2 + 1);
  const axisWidth = safeViewportWidth;
  const drawableWidth = Math.max(axisWidth - AXIS_PADDING_X_PX * 2, 1);

  const positionFor = (date: Date): number => {
    const ratio = daysBetween(rangeStart, date) / spanDays;
    return AXIS_PADDING_X_PX + ratio * drawableWidth;
  };

  const grouped = new Map<string, TimelineDayGroup>();
  for (const entry of dated) {
    const day = startOfDay(entry.date);
    const key = day.toISOString();
    const current = grouped.get(key);
    if (current) {
      current.items.push(entry.item);
      continue;
    }
    grouped.set(key, { date: day, items: [entry.item] });
  }

  const dayGroups = Array.from(grouped.values()).sort((a, b) => a.date.getTime() - b.date.getTime());
  const markers = dayGroups.map((group) => ({
    ...group,
    left: positionFor(group.date),
    isPast: group.date.getTime() < today.getTime(),
  }));

  const todayLeft = positionFor(today);
  const axisTop = Math.round(heightPx * 0.52);
  const activeMarker = activeIndex !== null ? markers[activeIndex] : null;
  const activeItems = activeMarker?.items ?? [];
  const activeDate = activeMarker?.date ?? null;

  return (
    <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
      <div ref={viewportRef} className="relative w-full" style={{ height: `${heightPx}px` }}>
        <div className="absolute inset-y-0 left-0 right-0 pointer-events-none" style={{ width: `${axisWidth}px` }}>
          <div className="absolute left-0 right-0 h-px bg-gray-300" style={{ top: `${axisTop}px` }} />

          <div
            className="absolute top-0 bottom-0 border-l-2 border-dashed border-primary"
            style={{ left: `${todayLeft}px` }}
            data-testid="plazos-timeline-today"
          >
            <span className="absolute -top-1 left-1 whitespace-nowrap text-[10px] font-semibold text-primary">Hoy</span>
          </div>
        </div>

        <div className="pointer-events-none absolute left-0 right-0 text-[10px] text-gray-500" style={{ top: `${axisTop + 16}px` }}>
          <span className="absolute -translate-x-1/2" style={{ left: `${AXIS_PADDING_X_PX}px` }}>
            {formatDate(rangeStart)}
          </span>
          <span className="absolute -translate-x-1/2" style={{ left: `${axisWidth - AXIS_PADDING_X_PX}px` }}>
            {formatDate(rangeEnd)}
          </span>
        </div>

        {markers.map(({ date, left, isPast, items }, index) => {
          const shortDate = date.toLocaleDateString("es-AR", { day: "2-digit", month: "short" });
          return (
            <div
              key={`${date.toISOString()}-${index}`}
              className="absolute"
              style={{ left: `${left}px`, top: `${axisTop - 7}px` }}
            >
              <button
                type="button"
                className={`relative h-4 w-4 -translate-x-1/2 rounded-full border-2 border-white shadow focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary ${isPast ? "bg-gray-400" : "bg-primary"}`}
                onClick={() => onToggleActive(index)}
                aria-label={`Hitos del ${formatDate(date)} (${items.length})`}
                data-testid="plazos-timeline-marker"
              />
              <span className="pointer-events-none absolute left-1/2 top-6 -translate-x-1/2 whitespace-nowrap rounded bg-white px-1 text-[10px] text-gray-600 ring-1 ring-gray-100">
                {shortDate}
              </span>
              {items.length > 1 ? (
                <span className="pointer-events-none absolute -right-3 -top-2 rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-fg">
                  {items.length}
                </span>
              ) : null}
            </div>
          );
        })}
      </div>

      {activeMarker && activeDate ? (
        <div className="mt-3 rounded-md border border-gray-200 bg-white p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Detalle del día</p>
          <p className="mt-0.5 text-sm font-semibold text-gray-900">{formatDate(activeDate)}</p>
          <ul className="mt-2 space-y-2">
            {activeItems.map((item, itemIndex) => {
              const confidenceLevel = getConfidenceLevel(item.confidence);
              const value = item.field_value ?? item.raw?.texto_original ?? item.raw?.expresion_relativa ?? "Sin detalle";
              return (
                <li key={`${item.field_name}-${itemIndex}`} className="rounded border border-gray-100 bg-gray-50 p-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium text-gray-900">{item.field_name}</p>
                    <FieldBadge level={confidenceLevel} />
                  </div>
                  <p className="mt-1 text-sm text-gray-700">{value}</p>
                  {item.raw?.lugar ? (
                    <p className="mt-1 flex items-center gap-1 text-xs text-gray-600">
                      <MapPin className="h-3 w-3" /> {item.raw.lugar}
                    </p>
                  ) : null}
                  {item.citations[0] ? (
                    <div className="mt-2">
                      <SourceEyeButton
                        pages={item.citations.map((citation) => citation.page)}
                        onClick={() => onViewSource(item)}
                      />
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </div>
      ) : (
        <p className="mt-3 text-sm text-gray-600">Seleccioná un punto para ver qué ocurre en ese día.</p>
      )}
    </div>
  );
}

/**
 * Línea de tiempo horizontal interactiva para Plazos Clave. Solo ubica en el
 * eje los plazos con `raw.fecha` (fecha calendaria literal) — nunca inventa
 * una fecha a partir de una expresion relativa ("10 dias habiles..."), esos
 * quedan listados aparte. El marcador de "Hoy" se calcula en cada render con
 * la fecha real del dispositivo, no la fecha en la que se corrio el analisis.
 */
export function PlazosTimeline({ items, narrativeSources = [], narrativeBullets = [], onViewSource }: PlazosTimelineProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const indexedBullets = useMemo(
    () => indexBulletsBySources(narrativeBullets, narrativeSources),
    [narrativeBullets, narrativeSources],
  );

  const extracted = useMemo(() => items.filter((item) => item.field_state === "extraido"), [items]);

  const { dated, undated } = useMemo(() => {
    const datedItems: DatedPlazo[] = [];
    const undatedItems: FieldItem[] = [];
    for (const item of extracted) {
      const parsed = item.raw?.fecha ? parseIsoDate(item.raw.fecha) : null;
      if (parsed) {
        datedItems.push({ item, date: parsed });
      } else {
        undatedItems.push(item);
      }
    }
    datedItems.sort((a, b) => a.date.getTime() - b.date.getTime());
    return { dated: datedItems, undated: undatedItems };
  }, [extracted]);

  const today = useMemo(() => startOfDay(new Date()), []);

  const undatedEntries = useMemo<UndatedEntry[]>(() => {
    const entries: UndatedEntry[] = [];
    for (const item of undated) {
      if (!undatedValue(item)) {
        continue;
      }
      const { label, value } = resolvePlazoDisplay(item, indexedBullets);
      entries.push({ item, label, value });
    }
    return entries;
  }, [undated, indexedBullets]);

  if (dated.length === 0 && undated.length === 0) {
    return (
      <p className="mt-3 text-sm text-gray-600" data-testid="plazos-timeline-empty">
        No se encontraron plazos en el pliego.
      </p>
    );
  }

  const handleViewSource = (item: FieldItem) => {
    const primary = item.citations[0];
    if (!primary || !onViewSource) {
      return;
    }
    // La categoría SÍ tiene narrativa con coordenadas ya calculadas (`CategorySection`); no mandar `sources: []` aunque esta vista use el flujo legado por-campo.
    const matched = matchSources(narrativeSources, item.citations);
    onViewSource({ citation: primary, citations: item.citations, sources: matched });
  };

  return (
    <div className="mt-3" data-testid="plazos-timeline">
      {dated.length > 0 ? (
        <>
          <div className="mb-2 flex items-center justify-end">
            <button
              type="button"
              className="flex items-center gap-1 rounded border border-gray-200 px-2 py-1 text-xs text-gray-700 hover:border-primary hover:text-primary"
              onClick={() => setIsFullscreen(true)}
              data-testid="plazos-timeline-fullscreen-open"
            >
              <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
              Pantalla completa
            </button>
          </div>

          <TimelineChart
            dated={dated}
            today={today}
            activeIndex={activeIndex}
            onToggleActive={(index) => setActiveIndex(activeIndex === index ? null : index)}
            onViewSource={handleViewSource}
            heightPx={COMPACT_HEIGHT_PX}
          />
        </>
      ) : null}

      {undatedEntries.length > 0 ? (
        <ul
          className={`divide-y divide-[rgba(0,60,107,.06)] ${dated.length > 0 ? "mt-3 border-t border-gray-200 pt-1" : ""}`}
          data-testid="plazos-sin-fecha"
        >
          {undatedEntries.map(({ item, label, value }, index) => (
            <li
              key={`${item.field_name}-${index}`}
              className="flex flex-col gap-1 py-2.5 first:pt-0 last:pb-0"
              data-testid="plazos-sin-fecha-item"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-[#003C6B]">{label}</span>
                {item.citations[0] ? (
                  <SourceEyeButton
                    pages={item.citations.map((citation) => citation.page)}
                    onClick={() => handleViewSource(item)}
                  />
                ) : null}
              </div>
              <p className="text-[13px] leading-relaxed text-[rgba(0,60,107,.68)]">
                {renderDetalleConNumerosEnNegrita(value)}
              </p>
            </li>
          ))}
        </ul>
      ) : null}

      {isFullscreen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-label="Línea de tiempo de Plazos Clave en pantalla completa"
          data-testid="plazos-timeline-modal"
        >
          <div className="flex max-h-[90vh] w-full max-w-6xl flex-col rounded-lg bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
              <h3 className="text-sm font-semibold text-gray-900">Línea de tiempo — Plazos Clave</h3>
              <button
                type="button"
                className="rounded p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-800"
                onClick={() => setIsFullscreen(false)}
                aria-label="Cerrar pantalla completa"
                data-testid="plazos-timeline-fullscreen-close"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              <TimelineChart
                dated={dated}
                today={today}
                activeIndex={activeIndex}
                onToggleActive={(index) => setActiveIndex(activeIndex === index ? null : index)}
                onViewSource={handleViewSource}
                heightPx={FULLSCREEN_HEIGHT_PX}
              />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
