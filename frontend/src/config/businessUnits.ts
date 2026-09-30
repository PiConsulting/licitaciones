export const BUSINESS_UNIT_COLORS = {
  CEDI: "#0099DB",
  PI: "#003C6B",
  Wemox: "#2F4EF8",
  Vulps: "#A966FF",
  Korex: "#7FF3DE",
} as const;

export type BusinessUnit = keyof typeof BUSINESS_UNIT_COLORS;

export const BUSINESS_UNITS = Object.keys(BUSINESS_UNIT_COLORS) as BusinessUnit[];

export const DEFAULT_BUSINESS_UNIT: BusinessUnit = BUSINESS_UNITS[0];

export const FALLBACK_BUSINESS_UNIT_COLOR = "#0099DB";

export function getBusinessUnitColor(unit: string | null | undefined): string {
  if (!unit) {
    return FALLBACK_BUSINESS_UNIT_COLOR;
  }
  return (BUSINESS_UNIT_COLORS as Record<string, string>)[unit] ?? FALLBACK_BUSINESS_UNIT_COLOR;
}
