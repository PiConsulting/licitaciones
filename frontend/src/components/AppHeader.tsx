import { useLocation } from "react-router-dom";

const PAGE_TITLES: Array<{ prefix: string; title: string }> = [
  { prefix: "/dashboard", title: "Historial" },
  { prefix: "/analyze", title: "Analizar nuevo pliego" },
  { prefix: "/analysis", title: "Análisis IA" },
];

function getPageTitle(pathname: string): string {
  const match = PAGE_TITLES.find(({ prefix }) => pathname.startsWith(prefix));
  return match?.title ?? "CedIA";
}

export function AppHeader() {
  const location = useLocation();
  const title = getPageTitle(location.pathname);

  return (
    <header className="sticky top-0 z-10 flex h-14 items-center border-b border-gray-200 bg-surface px-6">
      <h1 className="text-sm font-semibold text-gray-900">{title}</h1>
    </header>
  );
}
