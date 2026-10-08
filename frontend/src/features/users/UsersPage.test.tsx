import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";

import { createUser, fetchUsers, updateUser } from "../../api/users";
import { saveSession } from "../../auth/session";
import { BUSINESS_UNITS } from "../../config/businessUnits";
import { SUPERADMIN_ROLE } from "../../config/userRoles";
import type { SystemUser } from "../../types/users";
import { UsersPage } from "./UsersPage";
import { USERS_NEW_EVENT } from "./usersEvents";

const addToast = vi.hoisted(() => vi.fn());

vi.mock("../../components/ToastContainer", () => ({
  useToast: () => ({ addToast }),
}));

vi.mock("../../api/users", () => ({
  fetchUsers: vi.fn(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
}));

function buildUser(overrides: Partial<SystemUser>): SystemUser {
  return {
    id: "u-1",
    name: "Marcela Fernández",
    email: "m.fernandez@cedi.com.ar",
    role: "superadmin",
    business_unit: BUSINESS_UNITS[0],
    is_active: true,
    last_login_at: null,
    created_at: "2026-09-01T10:00:00Z",
    ...overrides,
  };
}

const USERS: SystemUser[] = [
  buildUser({}),
  buildUser({
    id: "u-2",
    name: "Lucía Benítez",
    email: "lbenitez@cedi.com.ar",
    role: "miembro",
    business_unit: BUSINESS_UNITS[1],
  }),
  buildUser({
    id: "u-3",
    name: "Martín Quiroga",
    email: "mquiroga@cedi.com.ar",
    role: "miembro",
    business_unit: BUSINESS_UNITS[2],
    is_active: false,
  }),
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <UsersPage />
    </QueryClientProvider>,
  );
}

describe("UsersPage", () => {
  beforeEach(() => {
    localStorage.clear();
    saveSession({
      name: "Marcela Fernández",
      email: "m.fernandez@cedi.com.ar",
      role: SUPERADMIN_ROLE,
      business_unit: BUSINESS_UNITS[0],
    });
    vi.mocked(fetchUsers).mockResolvedValue(USERS);
    vi.mocked(createUser).mockReset();
    vi.mocked(updateUser).mockReset();
    addToast.mockReset();
  });

  test("lista los usuarios con columnas, contador y KPIs", async () => {
    renderPage();

    expect(await screen.findByText("Lucía Benítez")).toBeInTheDocument();
    ["Usuario", "Unidad", "Rol", "Estado", "Último acceso", "Acciones"].forEach((column) => {
      expect(screen.getAllByText(column).length).toBeGreaterThan(0);
    });
    expect(screen.getByText("3 de 3 usuarios")).toBeInTheDocument();

    const summary = screen.getByRole("region", { name: "Resumen" });
    expect(within(summary).getByText("Usuarios").nextSibling).toHaveTextContent("3");
    expect(within(summary).getByText("Unidades").nextSibling).toHaveTextContent(String(BUSINESS_UNITS.length));
    expect(within(summary).getByText("Activos").nextSibling).toHaveTextContent("2");
    expect(within(summary).getByText("Suspendidos").nextSibling).toHaveTextContent("1");
  });

  test("muestra guion cuando el usuario nunca ingresó", async () => {
    renderPage();

    await screen.findByText("Lucía Benítez");
    expect(screen.getAllByText("—").length).toBe(3);
  });

  test("busca por nombre, email o unidad", async () => {
    renderPage();
    await screen.findByText("Lucía Benítez");
    const search = screen.getByRole("searchbox", { name: "Buscar usuarios" });

    fireEvent.change(search, { target: { value: "quiroga" } });
    expect(screen.getByText("1 de 3 usuarios")).toBeInTheDocument();

    fireEvent.change(search, { target: { value: BUSINESS_UNITS[1].toLowerCase() } });
    expect(screen.getByText("Lucía Benítez")).toBeInTheDocument();
    expect(screen.queryByText("Martín Quiroga")).not.toBeInTheDocument();

    fireEvent.change(search, { target: { value: "zzz" } });
    expect(screen.getByText("No hay usuarios para los filtros seleccionados.")).toBeInTheDocument();
  });

  test("filtra por unidad, rol y estado", async () => {
    renderPage();
    await screen.findByText("Lucía Benítez");

    fireEvent.change(screen.getByLabelText("Unidad"), { target: { value: BUSINESS_UNITS[2] } });
    expect(screen.getByText("1 de 3 usuarios")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Unidad"), { target: { value: "" } });

    fireEvent.change(screen.getByLabelText("Rol"), { target: { value: "miembro" } });
    expect(screen.getByText("2 de 3 usuarios")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Suspendido" }));
    expect(screen.getByText("1 de 3 usuarios")).toBeInTheDocument();
    expect(screen.getByText("Martín Quiroga")).toBeInTheDocument();
  });

  test("abre el panel de nuevo usuario desde el evento del header", async () => {
    renderPage();
    await screen.findByText("Lucía Benítez");

    window.dispatchEvent(new CustomEvent(USERS_NEW_EVENT));

    const dialog = await screen.findByRole("dialog", { name: "Nuevo usuario" });
    expect(within(dialog).getByText("Se da de alta en la unidad elegida.")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Unidad de negocio")).toBeInTheDocument();
    expect(within(dialog).getByRole("radio", { name: /Superadmin/ })).toBeInTheDocument();
    expect(within(dialog).getByRole("radio", { name: /Miembro/ })).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Contraseña temporal")).toBeInTheDocument();
  });

  test("crea un usuario con el rol y la unidad elegidos", async () => {
    vi.mocked(createUser).mockResolvedValue(buildUser({ id: "u-4" }));
    renderPage();
    await screen.findByText("Lucía Benítez");
    window.dispatchEvent(new CustomEvent(USERS_NEW_EVENT));
    const dialog = await screen.findByRole("dialog", { name: "Nuevo usuario" });

    fireEvent.change(within(dialog).getByLabelText("Nombre completo"), { target: { value: "Nuevo Miembro" } });
    fireEvent.change(within(dialog).getByLabelText("Email"), { target: { value: "nuevo@cedi.com.ar" } });
    fireEvent.change(within(dialog).getByLabelText("Unidad de negocio"), { target: { value: BUSINESS_UNITS[3] } });
    fireEvent.click(within(dialog).getByRole("radio", { name: /Miembro/ }));
    fireEvent.change(within(dialog).getByLabelText("Contraseña temporal"), { target: { value: "Clave1234" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Crear usuario" }));

    await waitFor(() => expect(createUser).toHaveBeenCalled());
    expect(vi.mocked(createUser).mock.calls[0][0]).toEqual({
      name: "Nuevo Miembro",
      email: "nuevo@cedi.com.ar",
      business_unit: BUSINESS_UNITS[3],
      role: "miembro",
      is_active: true,
      password: "Clave1234",
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(addToast).toHaveBeenCalledWith("success", "Usuario Nuevo Miembro creado.");
  });

  test("valida nombre, email y contraseña antes de crear", async () => {
    renderPage();
    await screen.findByText("Lucía Benítez");
    window.dispatchEvent(new CustomEvent(USERS_NEW_EVENT));
    const dialog = await screen.findByRole("dialog", { name: "Nuevo usuario" });

    fireEvent.click(within(dialog).getByRole("button", { name: "Crear usuario" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Ingresá el nombre completo");

    fireEvent.change(within(dialog).getByLabelText("Nombre completo"), { target: { value: "Ana" } });
    fireEvent.change(within(dialog).getByLabelText("Email"), { target: { value: "ana@cedi.com.ar" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Crear usuario" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Asignale una contraseña al usuario");

    fireEvent.change(within(dialog).getByLabelText("Contraseña temporal"), { target: { value: "corta" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Crear usuario" }));
    expect(within(dialog).getByRole("alert")).toHaveTextContent(
      "La contraseña debe tener al menos 8 caracteres y un número",
    );
    expect(createUser).not.toHaveBeenCalled();
  });

  test("con email duplicado muestra el error y mantiene el panel abierto", async () => {
    vi.mocked(createUser).mockRejectedValue({
      response: { data: { error: { code: "EMAIL_ALREADY_EXISTS", message: "Este email ya está registrado" } } },
    });
    renderPage();
    await screen.findByText("Lucía Benítez");
    window.dispatchEvent(new CustomEvent(USERS_NEW_EVENT));
    const dialog = await screen.findByRole("dialog", { name: "Nuevo usuario" });

    fireEvent.change(within(dialog).getByLabelText("Nombre completo"), { target: { value: "Ana" } });
    fireEvent.change(within(dialog).getByLabelText("Email"), { target: { value: "lbenitez@cedi.com.ar" } });
    fireEvent.change(within(dialog).getByLabelText("Contraseña temporal"), { target: { value: "Clave1234" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Crear usuario" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Este email ya está registrado");
    expect(screen.getByRole("dialog", { name: "Nuevo usuario" })).toBeInTheDocument();
    expect(addToast).toHaveBeenCalledWith("error", "Este email ya está registrado");
  });

  test("edita un usuario sin enviar contraseña cuando se deja vacía", async () => {
    vi.mocked(updateUser).mockResolvedValue(buildUser({ id: "u-2" }));
    renderPage();
    const row = (await screen.findByText("Lucía Benítez")).closest("div.grid") as HTMLElement;

    fireEvent.click(within(row).getByRole("button", { name: "Editar usuario" }));
    const dialog = await screen.findByRole("dialog", { name: "Editar usuario" });
    expect(within(dialog).getByText("Los cambios se aplican al guardar.")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Nueva contraseña (opcional)")).toBeInTheDocument();

    fireEvent.change(within(dialog).getByLabelText("Unidad de negocio"), { target: { value: BUSINESS_UNITS[4] } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => expect(updateUser).toHaveBeenCalled());
    const [userId, payload] = vi.mocked(updateUser).mock.calls[0];
    expect(userId).toBe("u-2");
    expect(payload).toEqual({
      name: "Lucía Benítez",
      email: "lbenitez@cedi.com.ar",
      business_unit: BUSINESS_UNITS[4],
      role: "miembro",
      is_active: true,
    });
    expect(addToast).toHaveBeenCalledWith("success", "Usuario Lucía Benítez actualizado.");
  });

  test("envía la contraseña nueva cuando se completa al editar", async () => {
    vi.mocked(updateUser).mockResolvedValue(buildUser({ id: "u-2" }));
    renderPage();
    const row = (await screen.findByText("Lucía Benítez")).closest("div.grid") as HTMLElement;

    fireEvent.click(within(row).getByRole("button", { name: "Editar usuario" }));
    const dialog = await screen.findByRole("dialog", { name: "Editar usuario" });
    fireEvent.change(within(dialog).getByLabelText("Nueva contraseña (opcional)"), {
      target: { value: "OtraClave99" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => expect(updateUser).toHaveBeenCalled());
    expect(vi.mocked(updateUser).mock.calls[0][1]).toMatchObject({ password: "OtraClave99" });
  });

  test("el botón Generar completa la contraseña y la deja visible", async () => {
    renderPage();
    await screen.findByText("Lucía Benítez");
    window.dispatchEvent(new CustomEvent(USERS_NEW_EVENT));
    const dialog = await screen.findByRole("dialog", { name: "Nuevo usuario" });

    fireEvent.click(within(dialog).getByRole("button", { name: "Generar" }));

    const field = within(dialog).getByLabelText("Contraseña temporal") as HTMLInputElement;
    expect(field.value).toHaveLength(12);
    expect(field.type).toBe("text");
  });

  test("suspende y reactiva desde la tabla", async () => {
    vi.mocked(updateUser).mockResolvedValue(buildUser({}));
    renderPage();
    const activeRow = (await screen.findByText("Lucía Benítez")).closest("div.grid") as HTMLElement;
    const suspendedRow = screen.getByText("Martín Quiroga").closest("div.grid") as HTMLElement;

    fireEvent.click(within(activeRow).getByRole("button", { name: "Suspender usuario" }));
    await waitFor(() => expect(updateUser).toHaveBeenCalledWith("u-2", { is_active: false }));
    await waitFor(() => expect(addToast).toHaveBeenCalledWith("success", "Usuario Lucía Benítez suspendido."));

    fireEvent.click(within(suspendedRow).getByRole("button", { name: "Reactivar usuario" }));
    await waitFor(() => expect(updateUser).toHaveBeenCalledWith("u-3", { is_active: true }));
    await waitFor(() => expect(addToast).toHaveBeenCalledWith("success", "Usuario Martín Quiroga reactivado."));
  });

  test("el superadmin no puede suspenderse a sí mismo ni quitarse el rol", async () => {
    renderPage();
    const ownRow = (await screen.findByText("Marcela Fernández")).closest("div.grid") as HTMLElement;

    expect(within(ownRow).getByRole("button", { name: "Suspender usuario" })).toBeDisabled();

    fireEvent.click(within(ownRow).getByRole("button", { name: "Editar usuario" }));
    const dialog = await screen.findByRole("dialog", { name: "Editar usuario" });
    expect(within(dialog).getByRole("radio", { name: /Miembro/ })).toBeDisabled();
    expect(within(dialog).getByLabelText("Estado")).toBeDisabled();
  });

  test("cierra el panel con Cancelar", async () => {
    renderPage();
    await screen.findByText("Lucía Benítez");
    window.dispatchEvent(new CustomEvent(USERS_NEW_EVENT));
    const dialog = await screen.findByRole("dialog", { name: "Nuevo usuario" });

    fireEvent.click(within(dialog).getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
