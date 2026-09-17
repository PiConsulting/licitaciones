import { describe, expect, test } from "vitest";

import { normalizePreviewSummary } from "./normalizePreviewSummary";

const CURRENCY_TITLE = "Licitación en pesos o dólares";
const GARANTIAS_TITLE = "Garantías o cauciones";

describe("normalizePreviewSummary", () => {
  test("moneda: dólares se muestra como USD", () => {
    expect(normalizePreviewSummary(CURRENCY_TITLE, "En dólares", "La cotización se hará en dólares estadounidenses.")).toBe(
      "USD",
    );
  });

  test("moneda: pesos se muestra como ARS", () => {
    expect(normalizePreviewSummary(CURRENCY_TITLE, "Pesos", "La cotización se hará en pesos argentinos.")).toBe("ARS");
  });

  test("moneda: si menciona ambas, muestra ambos códigos", () => {
    expect(
      normalizePreviewSummary(CURRENCY_TITLE, "Pesos o dólares", "Se admite cotizar en pesos o en dólares."),
    ).toBe("ARS / USD");
  });

  test("moneda: sin coincidencia mantiene el resumen original", () => {
    expect(normalizePreviewSummary(CURRENCY_TITLE, "Euros", "Se cotiza en euros.")).toBe("Euros");
  });

  test("garantias: una sola garantía muestra el porcentaje", () => {
    expect(
      normalizePreviewSummary(GARANTIAS_TITLE, "1% del monto", "Garantía de oferta del 1% del monto cotizado."),
    ).toBe("1%");
  });

  test("garantias: varias garantías muestran título corto + porcentaje por cada una", () => {
    const detail =
      "Garantía de oferta del 1% del monto cotizado, y garantía de cumplimiento de contrato del 5% del monto adjudicado.";
    expect(normalizePreviewSummary(GARANTIAS_TITLE, "1% y 5%", detail)).toBe("Oferta 1% · Cumplimiento 5%");
  });

  test("garantias: sin porcentaje detectable mantiene el resumen original", () => {
    expect(normalizePreviewSummary(GARANTIAS_TITLE, "A definir", "No se especifica un monto concreto.")).toBe(
      "A definir",
    );
  });

  test("no toca 'No informado'", () => {
    expect(normalizePreviewSummary(GARANTIAS_TITLE, "No informado", "No se encontró información.")).toBe(
      "No informado",
    );
  });

  test("no toca otros criterios", () => {
    expect(normalizePreviewSummary("Tiempo de entrega", "45 días", "Entrega en 45 días.")).toBe("45 días");
  });
});
