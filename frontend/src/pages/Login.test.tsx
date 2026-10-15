import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import Login from "./Login";

const navigateMock = vi.fn();
const loginMock = vi.fn();

vi.mock("../api/auth", () => ({
  login: (payload: unknown) => loginMock(payload),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

describe("Login", () => {
  beforeEach(() => {
    Object.defineProperty(window, "location", {
      writable: true,
      value: { href: "" },
    });
    localStorage.clear();
    loginMock.mockReset();
    navigateMock.mockReset();
  });

  test("muestra el selector de organización en lugar del formulario de password", () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );

    expect(screen.getByRole("button", { name: /PI Consulting/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /CEDI/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/email/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/contraseña/i)).not.toBeInTheDocument();
  });

  test("click en PI redirige al endpoint SSO del tenant pi", () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /PI Consulting/i }));

    expect(window.location.href).toContain("/auth/sso/pi/login");
  });

  test("click en CEDI redirige al endpoint SSO del tenant cedi", () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /CEDI/i }));

    expect(window.location.href).toContain("/auth/sso/cedi/login");
  });

  test("fallback temporal con contraseña: se puede mostrar y volver al selector SSO", () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /usar login con contraseña/i }));

    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/contraseña/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /volver a iniciar sesión con microsoft/i }));

    expect(screen.getByRole("button", { name: /PI Consulting/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/email/i)).not.toBeInTheDocument();
  });

  test("fallback temporal: login exitoso guarda sesión y navega al Home", async () => {
    loginMock.mockResolvedValueOnce({
      access_token: "jwt-token",
      token_type: "bearer",
      name: "Test User",
      email: "test@cedia.com",
      role: "superadmin",
      business_unit: null,
    });

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /usar login con contraseña/i }));
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "test@cedia.com" } });
    fireEvent.change(screen.getByLabelText(/contraseña/i), { target: { value: "Test1234!" } });
    fireEvent.click(screen.getByRole("button", { name: /^ingresar$/i }));

    await waitFor(() => {
      expect(localStorage.getItem("access_token")).toBe("jwt-token");
      expect(navigateMock).toHaveBeenCalledWith("/");
    });
  });

  test("fallback temporal: muestra error cuando las credenciales son inválidas", async () => {
    loginMock.mockRejectedValueOnce(new Error("invalid"));

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /usar login con contraseña/i }));
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "test@cedia.com" } });
    fireEvent.change(screen.getByLabelText(/contraseña/i), { target: { value: "WrongPassword1" } });
    fireEvent.click(screen.getByRole("button", { name: /^ingresar$/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Email o contraseña incorrectos");
    });
  });
});


