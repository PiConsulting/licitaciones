import type { UploadedFile } from "../../types/upload";

interface DocumentListItemProps {
  item: UploadedFile;
  selected: boolean;
  onSelect: () => void;
}

export function DocumentListItem({ item, selected, onSelect }: DocumentListItemProps) {
  return (
    <label
      className="flex cursor-pointer items-center gap-3 rounded-md border border-gray-200 bg-white p-3 hover:bg-gray-50"
      htmlFor={`primary-${item.id}`}
    >
      <input
        id={`primary-${item.id}`}
        type="radio"
        name="primary-document"
        checked={selected}
        onChange={onSelect}
        className="h-4 w-4 border-gray-300 text-primary focus:ring-primary"
      />
      <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-gray-900">{item.file.name}</p>
        <p className="text-xs text-gray-500">{item.sizeMb} MB</p>
      </div>
    </label>
  );
}
