import {
  ClipboardCheck,
  Clock,
  FileText,
  Info,
  Paperclip,
  Scale,
  Shield,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import type { CategoryId } from "../features/analysis-detail/types";

export const CATEGORY_ICONS: Record<CategoryId, LucideIcon> = {
  objeto_alcance: FileText,
  requisitos_admisibilidad: ClipboardCheck,
  garantias: Shield,
  plazos_clave: Clock,
  criterios_evaluacion: Scale,
  causales_rechazo: XCircle,
  anexos_obligatorios: Paperclip,
  datos_procedimiento: Info,
};

export const CATEGORY_NAMES: Record<CategoryId, string> = {
  objeto_alcance: "Objeto y Alcance",
  requisitos_admisibilidad: "Requisitos de Admisibilidad",
  garantias: "Garantías",
  plazos_clave: "Plazos Clave",
  criterios_evaluacion: "Criterios de Evaluación",
  causales_rechazo: "Causales de Rechazo",
  anexos_obligatorios: "Anexos Obligatorios",
  datos_procedimiento: "Datos del Procedimiento",
};

export const CRITICAL_CATEGORIES = new Set<CategoryId>([
  "plazos_clave",
  "garantias",
  "causales_rechazo",
]);

export const CATEGORY_ORDER: CategoryId[] = [
  "plazos_clave",
  "garantias",
  "causales_rechazo",
  "objeto_alcance",
  "requisitos_admisibilidad",
  "criterios_evaluacion",
  "anexos_obligatorios",
  "datos_procedimiento",
];
