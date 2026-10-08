/**
 * Formatea una fecha ISO (YYYY-MM-DD) a formato DD/MM/YYYY.
 * Parsea manualmente para evitar conversión de zona horaria.
 *
 * @param dateStr - String ISO date o null
 * @returns Fecha formateada o "Fecha pendiente"
 */
export function formatEventDate(dateStr: string | null): string {
  if (!dateStr) return "Fecha pendiente";

  const [year, month, day] = dateStr.split("T")[0].split("-");
  return `${day}/${month}/${year}`;
}
