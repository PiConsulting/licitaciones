import {
  BUSINESS_UNIT_COLORS,
  BUSINESS_UNITS,
  DEFAULT_BUSINESS_UNIT,
  FALLBACK_BUSINESS_UNIT_COLOR,
  getBusinessUnitColor,
} from "./businessUnits";

describe("businessUnits", () => {
  test("el listado se deriva del mapa de colores", () => {
    expect(BUSINESS_UNITS).toEqual(Object.keys(BUSINESS_UNIT_COLORS));
    expect(new Set(BUSINESS_UNITS).size).toBe(BUSINESS_UNITS.length);
  });

  test("la unidad por defecto es la primera del catálogo", () => {
    expect(DEFAULT_BUSINESS_UNIT).toBe(BUSINESS_UNITS[0]);
  });

  test("cada unidad tiene su color", () => {
    BUSINESS_UNITS.forEach((unit) => {
      expect(getBusinessUnitColor(unit)).toBe(BUSINESS_UNIT_COLORS[unit]);
    });
  });

  test("una unidad desconocida o vacía usa el color de respaldo", () => {
    expect(getBusinessUnitColor("Inexistente")).toBe(FALLBACK_BUSINESS_UNIT_COLOR);
    expect(getBusinessUnitColor(null)).toBe(FALLBACK_BUSINESS_UNIT_COLOR);
    expect(getBusinessUnitColor(undefined)).toBe(FALLBACK_BUSINESS_UNIT_COLOR);
  });
});
