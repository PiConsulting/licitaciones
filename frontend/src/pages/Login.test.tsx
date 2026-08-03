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
    localStorage.clear();
    loginMock.mockReset();
    navigateMock.mockReset();
  });

  test("renderiza formulario", () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );

    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/contraseña/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /registrate/i })).toHaveAttribute("href", "/register");
  });

  test("muestra error cuando credenciales inválidas", async () => {
    loginMock.mockRejectedValueOnce(new Error("invalid"));

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "test@cedia.com" } });
    fireEvent.change(screen.getByLabelText(/contraseña/i), { target: { value: "WrongPassword1" } });
    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Email o contraseña incorrectos");
    });
  });

  test("redirige y guarda token cuando login es exitoso", async () => {
    loginMock.mockResolvedValueOnce({ access_token: "jwt-token", token_type: "bearer" });

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "test@cedia.com" } });
    fireEvent.change(screen.getByLabelText(/contraseña/i), { target: { value: "Test1234!" } });
    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => {
      expect(localStorage.getItem("access_token")).toBe("jwt-token");
      expect(navigateMock).toHaveBeenCalledWith("/dashboard");
    });
  });
});
