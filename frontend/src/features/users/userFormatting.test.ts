import { formatLastAccess, generatePassword, getInitials, isValidPassword } from "./userFormatting";

describe("userFormatting", () => {
  const now = new Date(2026, 8, 30, 12, 0, 0);

  test("formatea el último acceso de hoy", () => {
    expect(formatLastAccess(new Date(2026, 8, 30, 9, 14).toISOString(), now)).toBe("Hoy, 09:14");
  });

  test("formatea el último acceso de ayer", () => {
    expect(formatLastAccess(new Date(2026, 8, 29, 18, 40).toISOString(), now)).toBe("Ayer, 18:40");
  });

  test("formatea fechas anteriores como dd/mm/aaaa", () => {
    expect(formatLastAccess(new Date(2026, 8, 24, 10, 0).toISOString(), now)).toBe("24/09/2026");
  });

  test("muestra guion cuando nunca ingresó o la fecha es inválida", () => {
    expect(formatLastAccess(null, now)).toBe("—");
    expect(formatLastAccess("no-es-fecha", now)).toBe("—");
  });

  test("calcula las iniciales con hasta dos palabras", () => {
    expect(getInitials("Marcela Fernández")).toBe("MF");
    expect(getInitials("agostina torres lopez")).toBe("AT");
    expect(getInitials("   ")).toBe("?");
  });

  test("valida la regla de contraseña", () => {
    expect(isValidPassword("Clave1234")).toBe(true);
    expect(isValidPassword("corta1")).toBe(false);
    expect(isValidPassword("sinnumeroaqui")).toBe(false);
  });

  test("genera contraseñas que cumplen la regla", () => {
    for (let index = 0; index < 50; index += 1) {
      const password = generatePassword();
      expect(password).toHaveLength(12);
      expect(isValidPassword(password)).toBe(true);
    }
  });
});
