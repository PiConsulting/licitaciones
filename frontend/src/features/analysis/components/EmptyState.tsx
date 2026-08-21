import { Link } from "react-router-dom";

import { Button } from "../../../components/Button";

export function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed border-gray-300 bg-white p-8 text-center">
      <h2 className="text-lg font-semibold text-gray-900">Todavía no hay análisis</h2>
      <p className="mt-2 text-sm text-gray-600">Subí tu primer pliego para empezar a construir el historial.</p>
      <div className="mt-5">
        <Link to="/analyze">
          <Button type="button">Ir al wizard de upload</Button>
        </Link>
      </div>
    </div>
  );
}
