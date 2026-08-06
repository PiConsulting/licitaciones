import type { HighlightCoordinates } from "../features/pdf-viewer/types";

function normalizeText(value: string): string {
  return value.replace(/\s+/g, " ").trim().toLowerCase();
}

export function findTextCoordinates(sourceText: string, searchText: string): HighlightCoordinates[] {
  const normalizedSource = normalizeText(sourceText);
  const normalizedSearch = normalizeText(searchText);

  if (!normalizedSource || !normalizedSearch) {
    return [];
  }

  if (!normalizedSource.includes(normalizedSearch)) {
    return [];
  }

  // React-PDF no expone coordenadas exactas sin procesar text layer;
  // devolvemos un highlight aproximado de línea completa para mantener verificabilidad visual.
  return [
    {
      x: 16,
      y: 64,
      width: 540,
      height: 24,
    },
  ];
}
