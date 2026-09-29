export type LensShape = "rect" | "circ";
export type LensSize = "s" | "m" | "l";

export interface LensConfig {
  enabled: boolean;
  zoom: number;
  shape: LensShape;
  size: LensSize;
}

export const LENS_ZOOMS = [1.5, 2, 3, 4] as const;

export const DEFAULT_LENS_CONFIG: LensConfig = {
  enabled: false,
  zoom: 2,
  shape: "rect",
  size: "m",
};

export const LENS_DIMENSIONS: Record<LensShape, Record<LensSize, [number, number]>> = {
  rect: { s: [220, 90], m: [300, 130], l: [380, 180] },
  circ: { s: [130, 130], m: [180, 180], l: [240, 240] },
};

export const LENS_MAX_RENDER_SCALE = 5;

export function formatLensZoom(zoom: number): string {
  return `${zoom}×`;
}

export function stepLensZoom(current: number, direction: 1 | -1): number {
  const index = LENS_ZOOMS.findIndex((value) => value === current);
  const base = index === -1 ? LENS_ZOOMS.findIndex((value) => value === DEFAULT_LENS_CONFIG.zoom) : index;
  const next = Math.max(0, Math.min(LENS_ZOOMS.length - 1, base + direction));
  return LENS_ZOOMS[next];
}
