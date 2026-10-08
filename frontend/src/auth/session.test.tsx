import { act, renderHook } from "@testing-library/react";

import { BUSINESS_UNITS } from "../config/businessUnits";
import { DEFAULT_USER_ROLE, SUPERADMIN_ROLE } from "../config/userRoles";
import { clearSession, readSession, saveSession, useSession } from "./session";

describe("session", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  test("guarda y lee el perfil con rol y unidad", () => {
    saveSession({
      name: " Ana Pérez ",
      email: "ana@cedia.com",
      role: SUPERADMIN_ROLE,
      business_unit: BUSINESS_UNITS[1],
    });

    expect(readSession()).toEqual({
      name: "Ana Pérez",
      email: "ana@cedia.com",
      role: SUPERADMIN_ROLE,
      businessUnit: BUSINESS_UNITS[1],
      isSuperadmin: true,
    });
  });

  test("un miembro no es superadmin", () => {
    saveSession({ email: "m@cedia.com", role: DEFAULT_USER_ROLE, business_unit: BUSINESS_UNITS[0] });

    expect(readSession().isSuperadmin).toBe(false);
  });

  test("sin unidad se elimina la unidad guardada", () => {
    saveSession({ email: "m@cedia.com", role: DEFAULT_USER_ROLE, business_unit: BUSINESS_UNITS[0] });
    saveSession({ email: "m@cedia.com", role: DEFAULT_USER_ROLE, business_unit: null });

    expect(readSession().businessUnit).toBe("");
  });

  test("clearSession borra todos los datos", () => {
    localStorage.setItem("access_token", "token");
    saveSession({ name: "Ana", email: "ana@cedia.com", role: SUPERADMIN_ROLE });

    clearSession();

    expect(localStorage.getItem("access_token")).toBeNull();
    expect(readSession().role).toBe("");
    expect(readSession().isSuperadmin).toBe(false);
  });

  test("useSession se actualiza cuando cambia la sesión", () => {
    const { result } = renderHook(() => useSession());
    expect(result.current.isSuperadmin).toBe(false);

    act(() => {
      saveSession({ email: "ana@cedia.com", role: SUPERADMIN_ROLE });
    });

    expect(result.current.isSuperadmin).toBe(true);
  });
});
