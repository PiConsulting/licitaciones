import { FileText } from "lucide-react";

const MAX_FILENAME_LENGTH = 40;

interface DocumentSourceDividerProps {
  documentName: string;
  showTopBorder?: boolean;
}

function truncateDocumentName(name: string): string {
  if (name.length <= MAX_FILENAME_LENGTH) {
    return name;
  }
  return `${name.slice(0, MAX_FILENAME_LENGTH - 3)}...`;
}

export function DocumentSourceDivider({ documentName, showTopBorder = true }: DocumentSourceDividerProps) {
  const isLongName = documentName.length > MAX_FILENAME_LENGTH;
  const displayName = truncateDocumentName(documentName);

  return (
    <div className="group py-2 md:py-4" data-testid="document-source-divider">
      <div className={`flex items-center gap-2 ${showTopBorder ? "border-t border-gray-200 pt-2 md:pt-4" : "pt-1"}`}>
        <FileText size={16} className="shrink-0 text-gray-600" aria-hidden="true" />
        <div className="relative min-w-0">
          <span
            data-testid="document-source-group-label"
            className="block truncate text-xs font-medium text-gray-600"
            title={documentName}
          >
            {displayName}
          </span>

          {isLongName ? (
            <div
              role="tooltip"
              className="pointer-events-none absolute left-0 top-full z-10 mt-1 max-w-xs rounded bg-gray-900 px-2 py-1 text-[11px] text-white opacity-0 shadow transition-opacity delay-500 group-hover:opacity-100"
            >
              {documentName}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
