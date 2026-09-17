import {
  AlertTriangle,
  Award,
  ArrowLeftRight,
  Clock,
  CreditCard,
  DollarSign,
  PackageCheck,
  ShieldCheck,
  Truck,
  Wallet,
  type LucideIcon,
} from "lucide-react";

/**
 * Ícono por criterio del preview (las 10 tarjetas de `PreviewTab`). Se
 * mapea por el título canónico (ver `PREVIEW_TITLES` en `PreviewTab.tsx`)
 * para dar una referencia visual rápida por tipo de dato, sin depender de
 * `CATEGORY_ICONS` (que cubre categorías más amplias, no estos criterios
 * puntuales). Un título que no matchea cae al ícono por defecto que define
 * quien lo consume.
 */
export const PREVIEW_CRITERION_ICONS: Record<string, LucideIcon> = {
  "Mantenimiento de oferta": Clock,
  "Tiempo de entrega": Truck,
  "Forma de pago": CreditCard,
  "Licitación en pesos o dólares": DollarSign,
  "Tipo de cambio": ArrowLeftRight,
  "Garantías o cauciones": ShieldCheck,
  "Multas o penalidades": AlertTriangle,
  "Anticipo financiero requerido": Wallet,
  "Requisitos técnicos o certificaciones excluyentes": Award,
  "Responsabilidad por costos logísticos o de instalación": PackageCheck,
};
