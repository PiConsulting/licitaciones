import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, vi } from "vitest";

import { ToastProvider } from "../components/ToastContainer";
import Register from "./Register";

const navigateMock = vi.fn();
const mutateAsyncMock = vi.fn();

vi.mock("../hooks/useRegister", () => ({
  useRegister: () => ({
    mutateAsync: mutateAsyncMock,
    isPending: false,
  }),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

describe("Register", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    mutateAsyncMock.mockReset();
    vi.useRealTimers();
  });

  function renderPage() {
    render(
      <MemoryRouter>
        <ToastProvider>
          <Register />
        </ToastProvider>
      </MemoryRouter>,
    );
  }

  test("renderiza formulario y link a login", () => {
    renderPage();

    expect(screen.getByLabelText(/nombre/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^contraseña$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/confirmar contraseña/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /registrarse/i })).toBeDisabled();
    expect(screen.getByRole("link", { name: /iniciar sesión/i })).toHaveAttribute("href", "/login");
  });

  test("muestra error de password débil en blur", async () => {
    renderPage();

    const passwordInput = screen.getByLabelText(/^contraseña$/i);
    fireEvent.change(passwordInput, { target: { value: "weak" } });
    fireEvent.blur(passwordInput);

    await waitFor(() => {
      expect(screen.getByText("La contraseña debe tener al menos 8 caracteres y un número")).toBeInTheDocument();
    });
  });

  test("muestra error cuando confirmación no coincide", async () => {
    renderPage();

    fireEvent.change(screen.getByLabelText(/^contraseña$/i), { target: { value: "SecurePass123" } });
    fireEvent.blur(screen.getByLabelText(/^contraseña$/i));
    fireEvent.change(screen.getByLabelText(/confirmar contraseña/i), {
      target: { value: "DifferentPass123" },
    });
    fireEvent.blur(screen.getByLabelText(/confirmar contraseña/i));

    await waitFor(() => {
      expect(screen.getByText("Las contraseñas no coinciden")).toBeInTheDocument();
    });
  });

  test("muestra toast éxito y redirige al login", async () => {
    mutateAsyncMock.mockResolvedValueOnce({
      id: "123",
      email: "juan@example.com",
      name: "Juan",
    });

    renderPage();

    fireEvent.change(screen.getByLabelText(/nombre/i), { target: { value: "Juan Pérez" } });
    fireEvent.blur(screen.getByLabelText(/nombre/i));
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "juan@example.com" } });
    fireEvent.blur(screen.getByLabelText(/email/i));
    fireEvent.change(screen.getByLabelText(/^contraseña$/i), { target: { value: "SecurePass123" } });
    fireEvent.blur(screen.getByLabelText(/^contraseña$/i));
    fireEvent.change(screen.getByLabelText(/confirmar contraseña/i), { target: { value: "SecurePass123" } });
    fireEvent.blur(screen.getByLabelText(/confirmar contraseña/i));

    const submitButton = screen.getByRole("button", { name: /registrarse/i });
    await waitFor(() => {
      expect(submitButton).toBeEnabled();
    });

    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText("Cuenta creada exitosamente")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith("/login");
    }, { timeout: 3000 });
  });

  test("muestra toast error cuando email está duplicado", async () => {
    mutateAsyncMock.mockRejectedValueOnce({
      response: {
        status: 409,
        data: {
          detail: {
            error: {
              code: "EMAIL_ALREADY_EXISTS",
              message: "Este email ya está registrado",
            },
          },
        },
      },
    });

    renderPage();

    fireEvent.change(screen.getByLabelText(/nombre/i), { target: { value: "Juan Pérez" } });
    fireEvent.blur(screen.getByLabelText(/nombre/i));
    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: "juan@example.com" } });
    fireEvent.blur(screen.getByLabelText(/email/i));
    fireEvent.change(screen.getByLabelText(/^contraseña$/i), { target: { value: "SecurePass123" } });
    fireEvent.blur(screen.getByLabelText(/^contraseña$/i));
    fireEvent.change(screen.getByLabelText(/confirmar contraseña/i), { target: { value: "SecurePass123" } });
    fireEvent.blur(screen.getByLabelText(/confirmar contraseña/i));

    const submitButton = screen.getByRole("button", { name: /registrarse/i });
    await waitFor(() => {
      expect(submitButton).toBeEnabled();
    });

    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mutateAsyncMock).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(screen.getByText("Este email ya está registrado")).toBeInTheDocument();
    });
  });
});
