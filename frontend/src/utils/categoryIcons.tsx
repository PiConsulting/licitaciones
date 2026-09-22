import {
  AlertTriangle,
  Ban,
  ClipboardCheck,
  Clock,
  FileText,
  Info,
  Paperclip,
  Scale,
  Shield,
  type LucideIcon,
} from "lucide-react";

import type { CategoryId } from "../features/analysis-detail/types";

export const CATEGORY_ICONS: Record<CategoryId, LucideIcon> = {
  objeto_alcance: FileText,
  riesgos: AlertTriangle,
  requisitos_admisibilidad: ClipboardCheck,
  garantias: Shield,
  plazos_clave: Clock,
  criterios_evaluacion: Scale,
  causales_rechazo: Ban,
  anexos_obligatorios: Paperclip,
  datos_procedimiento: Info,
};

export const CATEGORY_NAMES: Record<CategoryId, string> = {
  objeto_alcance: "Objeto y Alcance",
  riesgos: "Riesgos",
  requisitos_admisibilidad: "Requisitos de Admisibilidad",
  garantias: "Garantías",
  plazos_clave: "Plazos Clave",
  criterios_evaluacion: "Criterios de Evaluación",
  causales_rechazo: "Causales de Rechazo",
  anexos_obligatorios: "Anexos Obligatorios",
  datos_procedimiento: "Datos del Procedimiento",
};

export const CRITICAL_CATEGORIES = new Set<CategoryId>([
  "riesgos",
  "plazos_clave",
  "garantias",
  "causales_rechazo",
]);

/** Categorías con ítems discretos (ej. anexos) preferidas en lista por el fallback local sin LLM; el backend no fuerza formato por categoría (ver narrativeSynthesis.ts). */
export const CHECKLIST_CATEGORIES = new Set<CategoryId>(["anexos_obligatorios"]);

/** Orden canónico de visualización; datos_procedimiento queda fuera del checklist y las categorías críticas no determinan el orden. */
export const CATEGORY_ORDER: CategoryId[] = [
  "objeto_alcance",
  "riesgos",
  "requisitos_admisibilidad",
  "garantias",
  "plazos_clave",
  "criterios_evaluacion",
  "causales_rechazo",
  "anexos_obligatorios",
];
