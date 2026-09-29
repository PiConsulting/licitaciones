import type { UploadedFile } from "../../types/upload";

interface DocumentListItemProps {
  item: UploadedFile;
  selected: boolean;
  onSelect: () => void;
}

export function DocumentListItem({ item, selected, onSelect }: DocumentListItemProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      aria-label={item.file.name}
      onClick={onSelect}
      className={[
        "flex w-full items-center gap-[14px] rounded-xl border-[1.5px] p-[14px_16px] text-left transition-all",
        selected ? "border-cedi-navy bg-[#F4F9FC]" : "border-cedi-navy-12 bg-white hover:border-cedi-celeste",
      ].join(" ")}
    >
      <span
        className={[
          "inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 bg-white",
          selected ? "border-cedi-navy" : "border-cedi-navy-30",
        ].join(" ")}
        aria-hidden="true"
      >
        <span className={["h-2.5 w-2.5 rounded-full", selected ? "bg-cedi-navy" : "bg-transparent"].join(" ")} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-cedi-navy">{item.file.name}</p>
        <p className="mt-0.5 text-xs text-cedi-navy-55">{item.pagesLabel}, {item.sizeMb} MB</p>
      </div>
      {selected ? (
        <span className="rounded-full bg-cedi-navy px-2.5 py-1 text-[11px] font-bold uppercase tracking-[0.1em] text-white">
          Principal
        </span>
      ) : null}
    </button>
  );
}
