import type { Citation, NarrativeBlockData, NarrativeSource } from "../types";

export function sourceToCitation(source: NarrativeSource): Citation {
  return {
    text: source.text,
    page: source.page,
    document_id: source.document_id,
    document_name: source.document_name,
  };
}

export function filterVerifiedSources(sources: NarrativeSource[]): NarrativeSource[] {
  return sources.filter((source) => !source.unverified);
}

export function collectParagraphSourceIds(blocks: NarrativeBlockData[]): Set<number> {
  const ids = new Set<number>();
  for (const block of blocks) {
    if (block.type === "paragraph") {
      block.source_ids.forEach((id) => ids.add(id));
    }
  }
  return ids;
}

export function collectReferencedSourceIds(blocks: NarrativeBlockData[]): Set<number> {
  const ids = new Set<number>();
  for (const block of blocks) {
    if (block.type === "paragraph") {
      block.source_ids.forEach((id) => ids.add(id));
    } else if (block.type === "bullet_list") {
      block.items.forEach((item) => item.source_ids.forEach((id) => ids.add(id)));
    } else {
      block.rows.forEach((row) => row.source_ids.forEach((id) => ids.add(id)));
    }
  }
  return ids;
}

export function resolveSourceIdsToSources(sourceIds: number[], sourceById: Map<number, NarrativeSource>): NarrativeSource[] {
  return sourceIds
    .map((id) => sourceById.get(id))
    .filter((source): source is NarrativeSource => source !== undefined);
}
