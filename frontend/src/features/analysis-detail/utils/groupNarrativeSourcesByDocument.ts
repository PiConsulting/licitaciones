import type { NarrativeSource } from "../types";

export interface NarrativeSourceGroup {
  documentId: string;
  documentName: string;
  displayName: string;
  isPrimary: boolean;
  sources: NarrativeSource[];
}

function cleanDocumentName(name: string): string {
  return name
    .replace(/\.pdf$/i, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function looksPrimaryDocument(name: string): boolean {
  const normalized = cleanDocumentName(name).toLocaleLowerCase("es");
  return normalized.startsWith("pliego");
}

export function groupNarrativeSourcesByDocument(sources: NarrativeSource[]): NarrativeSourceGroup[] {
  const grouped = new Map<string, NarrativeSourceGroup>();

  for (const source of sources) {
    const existing = grouped.get(source.document_id);
    if (existing) {
      existing.sources.push(source);
      continue;
    }

    grouped.set(source.document_id, {
      documentId: source.document_id,
      documentName: source.document_name,
      displayName: cleanDocumentName(source.document_name),
      isPrimary: looksPrimaryDocument(source.document_name),
      sources: [source],
    });
  }

  const groups = Array.from(grouped.values());
  groups.sort((left, right) => {
    if (left.isPrimary && !right.isPrimary) {
      return -1;
    }
    if (!left.isPrimary && right.isPrimary) {
      return 1;
    }

    return left.displayName.localeCompare(right.displayName, "es", { sensitivity: "base" });
  });

  return groups;
}
