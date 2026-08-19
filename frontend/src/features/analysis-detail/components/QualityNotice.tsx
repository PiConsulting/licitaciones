import { AlertTriangle } from "lucide-react";

import type { CategoryQuality } from "../types";

interface QualityNoticeProps {
  quality?: CategoryQuality;
}

function plural(cantidad: number, singular: string, plural_: string): string {
  return cantidad === 1 ? singular : plural_;
}

/**
 * Por qué esta categoría quedó incompleta (ATR-03).
 *
 * El pipeline descarta correctamente los hallazgos cuya cita no se puede
 * verificar contra el pliego. El problema era que ese descarte no se veía: la
 * categoría llegaba marcada "parcial" y no había forma de distinguir
 *
 *   "el pliego casi no habla de esto"   de   "el modelo produjo tres hallazgos
 *                                             que no pudimos respaldar"
 *
 * y esa diferencia es justamente la señal de si conviene desconfiar de lo que
 * quedó. Antes vivía sólo en un log del backend.
 */
export function QualityNotice({ quality }: QualityNoticeProps) {
  if (!quality) {
    return null;
  }

  const descartados = (quality.descartados_sin_evidencia ?? 0) + (quality.descartados_por_formato ?? 0);
  const rescatados = quality.con_evidencia_rescatada ?? 0;

  if (descartados === 0 && rescatados === 0) {
    return null;
  }

  const avisos: string[] = [];
  if (descartados > 0) {
    avisos.push(
      `${descartados} ${plural(descartados, "hallazgo no pudo", "hallazgos no pudieron")} respaldarse con el pliego y ${plural(descartados, "fue omitido", "fueron omitidos")}`,
    );
  }
  if (rescatados > 0) {
    avisos.push(
      `${rescatados} ${plural(rescatados, "cita no coincide", "citas no coinciden")} con lo que el modelo declaró como evidencia`,
    );
  }

  return (
    <p
      className="mt-2 flex items-start gap-1.5 text-xs text-warning"
      data-testid="category-quality-notice"
    >
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <span>{`${avisos.join(". ")}. Conviene revisar el original.`}</span>
    </p>
  );
}
