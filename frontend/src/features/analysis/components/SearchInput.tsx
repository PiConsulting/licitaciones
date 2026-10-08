interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
}

export function SearchInput({ value, onChange }: SearchInputProps) {
  return (
    <label className="flex h-9 min-w-52 flex-1 items-center gap-2 rounded-full border-[1.5px] border-cedi-navy-20 bg-white px-3.5">
      <span className="sr-only">Buscar</span>
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        className="h-[15px] w-[15px] flex-none text-cedi-navy-55"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        <circle cx="11" cy="11" r="8" />
        <path d="M21 21L16.7 16.7" strokeLinecap="round" />
      </svg>
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Buscar por pliego u organismo"
        className="min-w-0 flex-1 border-0 bg-transparent text-[13px] text-cedi-navy placeholder:text-cedi-navy-55 focus-visible:outline-none"
      />
    </label>
  );
}
