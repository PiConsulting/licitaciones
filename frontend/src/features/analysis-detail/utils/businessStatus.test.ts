import {
  amountToInput,
  describeAmountDifference,
  formatAmountInput,
  formatIsoDate,
  formatMoney,
  getPendingActionText,
  parseAmountInput,
  resolveBusinessStatus,
} from "./businessStatus";

describe("businessStatus utils", () => {
  it("resuelve estados nulos o desconocidos como en_analisis", () => {
    expect(resolveBusinessStatus(null)).toBe("en_analisis");
    expect(resolveBusinessStatus(undefined)).toBe("en_analisis");
    expect(resolveBusinessStatus("otro_estado")).toBe("en_analisis");
    expect(resolveBusinessStatus(" presentada ")).toBe("presentada");
  });

  it("solo hay acción pendiente en decisión, revisión y presentada", () => {
    expect(getPendingActionText("pendiente_decision")).not.toBeNull();
    expect(getPendingActionText("en_revision")).not.toBeNull();
    expect(getPendingActionText("presentada")).not.toBeNull();
    expect(getPendingActionText("en_analisis")).toBeNull();
    expect(getPendingActionText("no_aprobada")).toBeNull();
    expect(getPendingActionText("ganada")).toBeNull();
    expect(getPendingActionText("perdida")).toBeNull();
  });

  it("formatea y parsea montos con separador de miles", () => {
    expect(formatAmountInput("18500000")).toBe("18.500.000");
    expect(formatAmountInput("abc")).toBe("");
    expect(parseAmountInput("18.500.000")).toBe(18500000);
    expect(parseAmountInput("")).toBeNull();
    expect(amountToInput(179800000)).toBe("179.800.000");
    expect(amountToInput(null)).toBe("");
  });

  it("formatea fechas ISO y montos por moneda", () => {
    expect(formatIsoDate("2026-09-18")).toBe("18/09/2026");
    expect(formatIsoDate("2026-09-18T10:00:00Z")).toBe("18/09/2026");
    expect(formatIsoDate(null)).toBe("—");
    expect(formatMoney(1500000, "ARS")).toBe("$ 1.500.000");
    expect(formatMoney(1500000, "USD")).toBe("US$ 1.500.000");
    expect(formatMoney(null)).toBe("—");
  });

  it("describe la diferencia entre adjudicado y ofertado", () => {
    expect(describeAmountDifference(100, 100)).toBe("Igual a lo ofertado");
    expect(describeAmountDifference(900, 1000)).toBe("$ 100 menos");
    expect(describeAmountDifference(1100, 1000)).toBe("$ 100 más");
    expect(describeAmountDifference(null, 1000)).toBe("—");
  });
});
