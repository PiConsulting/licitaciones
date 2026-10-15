import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

import SsoCallback from "./SsoCallback";

const navigateMock = vi.fn();
const exchangeSsoCodeMock = vi.fn();

vi.mock("../api/auth", () => ({
  exchangeSsoCode: (code: string) => exchangeSsoCodeMock(code),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

function renderWithCode(search: string) {
  return render(
    <MemoryRouter initialEntries={[`/sso/callback${search}`]}>
      <Routes>
        <Route path="/sso/callback" element={<SsoCallback />} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderWithCodeInStrictMode(search: string) {
  return render(
    <StrictMode>
      <MemoryRouter initialEntries={[`/sso/callback${search}`]}>
        <Routes>
          <Route path="/sso/callback" element={<SsoCallback />} />
        </Routes>
      </MemoryRouter>
    </StrictMode>,
  );
}

describe("SsoCallback", () => {
  beforeEach(() => {
    localStorage.clear();
    navigateMock.mockReset();
    exchangeSsoCodeMock.mockReset();
  });

  test("canjea el código, guarda la sesión y navega al Home", async () => {
    exchangeSsoCodeMock.mockResolvedValueOnce({
      access_token: "jwt-token",
      token_type: "bearer",
      name: "Nueva Persona",
      email: "nueva.persona@piconsulting.com.ar",
      role: "miembro",
      business_unit: "PI",
    });

    renderWithCode("?code=abc123");

    await waitFor(() => {
      expect(localStorage.getItem("access_token")).toBe("jwt-token");
      expect(localStorage.getItem("user_email")).toBe("nueva.persona@piconsulting.com.ar");
      expect(navigateMock).toHaveBeenCalledWith("/");
    });
  });

  test("sin código en la URL, muestra error y no persiste sesión", async () => {
    renderWithCode("");

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Falta el código de inicio de sesión");
    });
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(exchangeSsoCodeMock).not.toHaveBeenCalled();
  });

  test("código inválido/expirado muestra mensaje de error y no persiste sesión", async () => {
    exchangeSsoCodeMock.mockRejectedValueOnce({
      response: { data: { error: { code: "SSO_CODE_INVALID" } } },
    });

    renderWithCode("?code=expirado");

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/expiró o ya fue usado/i);
    });
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(screen.getByRole("link", { name: /volver a iniciar sesión/i })).toHaveAttribute(
      "href",
      "/login",
    );
  });

  test("bajo StrictMode (doble invocación de efectos en dev) solo canjea el code una vez", async () => {
    exchangeSsoCodeMock.mockResolvedValueOnce({
      access_token: "jwt-token",
      token_type: "bearer",
      name: "Nueva Persona",
      email: "nueva.persona@piconsulting.com.ar",
      role: "miembro",
      business_unit: "PI",
    });

    renderWithCodeInStrictMode("?code=abc123");

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith("/");
    });

    // El code de intercambio es de un solo uso: si el guard no existiera, StrictMode
    // llamaría exchangeSsoCode 2 veces y la 2da siempre fallaría con 410 (ver sso.py).
    expect(exchangeSsoCodeMock).toHaveBeenCalledTimes(1);
  });
});

