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

/**
 * Categorías donde cada ítem suele ser un hecho discreto (un anexo) en vez de
 * una idea narrativa única — usada solo por el fallback local de síntesis
 * (`narrativeSynthesis.ts`, cuando el backend todavía no mandó `narrative`
 * para esa categoría) para preferir lista sobre párrafo. El backend real
 * (`_response_base.txt`) no tiene esta ni ninguna otra lista fija por
 * categoría: el LLM elige el formato libremente según el contenido de cada
 * pliego. Este fallback es más simple porque no es un LLM, pero tampoco debe
 * forzar un formato único por categoría — ver `narrativeSynthesis.ts`.
 */
export const CHECKLIST_CATEGORIES = new Set<CategoryId>(["anexos_obligatorios"]);

/**
 * Orden canónico de categorías para visualización.
 * Define el flujo de lectura de negocio del pliego.
 * 
 * NOTA: datos_procedimiento NO está incluido en el checklist principal.
 * Las categorías críticas mantienen su significado para validación
 * pero NO gobiernan el orden visual.
 */
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
