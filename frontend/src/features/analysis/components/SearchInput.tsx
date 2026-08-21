interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
}

export function SearchInput({ value, onChange }: SearchInputProps) {
  return (
    <label className="flex flex-1 min-w-52 flex-col gap-1">
      <span className="text-sm font-medium text-gray-700">Buscar</span>
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Buscar por pliego u organismo"
        className="h-10 rounded-md border border-gray-200 px-3 py-2 text-sm focus-visible:border-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
      />
    </label>
  );
}
