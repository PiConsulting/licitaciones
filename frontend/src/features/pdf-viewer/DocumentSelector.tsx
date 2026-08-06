import type { ViewerDocument } from "./types";

interface DocumentSelectorProps {
  documents: ViewerDocument[];
  value: string;
  onChange: (documentId: string) => void;
}

export function DocumentSelector({ documents, value, onChange }: DocumentSelectorProps) {
  if (documents.length <= 1) {
    return null;
  }

  return (
    <label className="ml-auto flex items-center gap-2 text-xs text-gray-700">
      Documento
      <select
        className="rounded border border-gray-300 bg-white px-2 py-1"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-label="Documento activo"
      >
        {documents.map((document) => (
          <option key={document.id} value={document.id}>
            {document.filename}
          </option>
        ))}
      </select>
    </label>
  );
}
