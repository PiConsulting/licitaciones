import { Search } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { useSession } from "../../auth/session";
import { useToast } from "../../components/ToastContainer";
import { BUSINESS_UNITS, getBusinessUnitColor } from "../../config/businessUnits";
import { USER_ROLE_CONFIG, USER_ROLES } from "../../config/userRoles";
import type { SystemUser } from "../../types/users";
import { useUpdateUserMutation, useUsersQuery } from "./hooks/useUsers";
import { UserDrawer } from "./UserDrawer";
import { USERS_NEW_EVENT } from "./usersEvents";
import { formatLastAccess, getInitials } from "./userFormatting";

type StatusName = "Activo" | "Suspendido";

const STATUS_STYLES: Record<StatusName, { fg: string; bg: string }> = {
  Activo: { fg: "#0B6B58", bg: "rgba(127,243,222,.4)" },
  Suspendido: { fg: "#B42318", bg: "rgba(220,38,38,.1)" },
};
const STATUS_NAMES = Object.keys(STATUS_STYLES) as StatusName[];

const GRID_COLUMNS = "grid-cols-[minmax(0,1.5fr)_minmax(0,1.1fr)_200px_130px_130px_96px]";
const HEAD_CELL_CLASS = "text-[10px] font-bold uppercase tracking-[.14em] text-cedi-navy-55";
const FILTER_SELECT_CLASS =
  "h-8 rounded-full border-[1.5px] border-cedi-navy-20 bg-white py-0 pl-3 pr-8 text-[13px] font-semibold text-cedi-navy focus:border-cedi-celeste focus:outline-none focus:ring-0";
const ICON_BUTTON_CLASS =
  "inline-flex h-9 w-9 items-center justify-center rounded-lg border-0 bg-transparent text-cedi-navy-68 hover:bg-[rgba(0,60,107,.08)] hover:text-cedi-navy";

const BAN_PATH = "M12 2a10 10 0 1 0 0 20a10 10 0 1 0 0-20 M4.9 4.9l14.2 14.2";
const CHECK_PATH = "M20 6 9 17l-5-5";

function statusOf(user: SystemUser): StatusName {
  return user.is_active ? "Activo" : "Suspendido";
}

function ActionIcon({ children }: { children: ReactNode }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export function UsersPage() {
  const session = useSession();
  const usersQuery = useUsersQuery();
  const updateMutation = useUpdateUserMutation();
  const [query, setQuery] = useState("");
  const [unitFilter, setUnitFilter] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusName[]>([]);
  const [drawer, setDrawer] = useState<{ user: SystemUser | null } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const { addToast } = useToast();

  useEffect(() => {
    const openNew = () => setDrawer({ user: null });
    window.addEventListener(USERS_NEW_EVENT, openNew);
    return () => window.removeEventListener(USERS_NEW_EVENT, openNew);
  }, []);

  const users = useMemo(() => usersQuery.data ?? [], [usersQuery.data]);

  const visibleUsers = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return users.filter(
      (user) =>
        (!normalizedQuery ||
          [user.name, user.email, user.business_unit ?? ""].join(" ").toLowerCase().includes(normalizedQuery)) &&
        (!unitFilter || user.business_unit === unitFilter) &&
        (!roleFilter || user.role === roleFilter) &&
        (statusFilter.length === 0 || statusFilter.includes(statusOf(user))),
    );
  }, [users, query, unitFilter, roleFilter, statusFilter]);

  const kpis = [
    { label: "Usuarios", value: users.length },
    { label: "Unidades", value: BUSINESS_UNITS.length },
    { label: "Activos", value: users.filter((user) => user.is_active).length },
    { label: "Suspendidos", value: users.filter((user) => !user.is_active).length },
  ];

  async function handleToggleStatus(user: SystemUser) {
    setActionError(null);
    try {
      await updateMutation.mutateAsync({ userId: user.id, payload: { is_active: !user.is_active } });
      addToast("success", user.is_active ? `Usuario ${user.name} suspendido.` : `Usuario ${user.name} reactivado.`);
    } catch (caught) {
      const message = (caught as { response?: { data?: { error?: { message?: string } } } })?.response?.data?.error
        ?.message;
      const fallback = "No se pudo actualizar el estado del usuario";
      setActionError(message ?? fallback);
      addToast("error", message ?? fallback);
    }
  }

  function toggleStatusFilter(name: StatusName) {
    setStatusFilter((current) =>
      current.includes(name) ? current.filter((item) => item !== name) : [...current, name],
    );
  }

  const isEmpty = !usersQuery.isLoading && !usersQuery.isError && visibleUsers.length === 0;

  return (
    <div className="flex flex-col gap-5 leading-[normal]">
      <section className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="m-0 font-display text-[28px] font-bold leading-[1.15] tracking-[-0.015em] text-cedi-navy">
            Usuarios del sistema
          </h1>
          <p className="m-0 mt-1.5 text-sm leading-normal text-cedi-navy-68">
            Todos los usuarios de todas las unidades de negocio. Creá, editá o suspendé accesos.
          </p>
        </div>
        <label className="flex h-10 max-w-[420px] flex-[1_1_260px] items-center gap-2 rounded-full border-[1.5px] border-cedi-navy-20 bg-white px-4">
          <Search size={16} strokeWidth={2} stroke="rgba(0,60,107,.45)" aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar por nombre, email o unidad de negocio"
            aria-label="Buscar usuarios"
            className="min-w-0 flex-1 border-0 bg-transparent p-0 text-[13px] text-cedi-navy outline-none focus:ring-0"
          />
        </label>
      </section>

      <section aria-label="Resumen" className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3">
        {kpis.map((kpi) => (
          <div key={kpi.label} className="rounded-2xl border border-cedi-navy-12 bg-white px-5 py-4">
            <div className={HEAD_CELL_CLASS}>{kpi.label}</div>
            <div className="mt-1.5 font-display text-[28px] font-bold tracking-[-0.02em] text-cedi-navy">
              {kpi.value}
            </div>
          </div>
        ))}
      </section>

      <section className="flex flex-wrap items-center gap-x-4 gap-y-2" aria-label="Filtros de usuarios">
        <label className="flex items-center gap-2 text-[13px] text-cedi-navy-68">
          Unidad
          <select value={unitFilter} onChange={(event) => setUnitFilter(event.target.value)} className={FILTER_SELECT_CLASS}>
            <option value="">Todas</option>
            {BUSINESS_UNITS.map((unit) => (
              <option key={unit} value={unit}>
                {unit}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-[13px] text-cedi-navy-68">
          Rol
          <select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)} className={FILTER_SELECT_CLASS}>
            <option value="">Todos</option>
            {USER_ROLES.map((role) => (
              <option key={role} value={role}>
                {USER_ROLE_CONFIG[role].label}
              </option>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <span className="mr-1 text-xs font-bold uppercase tracking-[.14em] text-cedi-navy-55">Estado</span>
          {STATUS_NAMES.map((name) => {
            const active = statusFilter.includes(name);
            return (
              <button
                key={name}
                type="button"
                aria-pressed={active}
                onClick={() => toggleStatusFilter(name)}
                className={[
                  "h-8 rounded-full border-[1.5px] px-3.5 text-[13px] font-semibold",
                  active
                    ? "border-cedi-navy bg-cedi-navy text-white"
                    : "border-cedi-navy-20 bg-white text-cedi-navy hover:border-cedi-celeste",
                ].join(" ")}
              >
                {name}
              </button>
            );
          })}
        </div>
        <span className="ml-auto text-[13px] text-cedi-navy-68">
          {visibleUsers.length} de {users.length} usuarios
        </span>
      </section>

      {actionError ? (
        <p role="alert" className="m-0 text-[13px] font-semibold text-[#B42318]">
          {actionError}
        </p>
      ) : null}

      <section aria-label="Usuarios" className="overflow-x-auto rounded-2xl border border-cedi-navy-12 bg-white">
        <div className="min-w-[930px]">
          <div
            className={`grid ${GRID_COLUMNS} items-center gap-4 rounded-t-2xl border-b border-cedi-navy-12 bg-cedi-surface-tint px-5 py-3`}
          >
            <span className={HEAD_CELL_CLASS}>Usuario</span>
            <span className={HEAD_CELL_CLASS}>Unidad</span>
            <span className={HEAD_CELL_CLASS}>Rol</span>
            <span className={HEAD_CELL_CLASS}>Estado</span>
            <span className={HEAD_CELL_CLASS}>Último acceso</span>
            <span className={`${HEAD_CELL_CLASS} text-right`}>Acciones</span>
          </div>

          {visibleUsers.map((user) => {
            const status = statusOf(user);
            const statusStyle = STATUS_STYLES[status];
            const roleConfig = USER_ROLE_CONFIG[user.role];
            const unitColor = getBusinessUnitColor(user.business_unit);
            const toggleLabel = user.is_active ? "Suspender usuario" : "Reactivar usuario";
            const isOwnUser = user.email.toLowerCase() === session.email.toLowerCase();
            return (
              <div
                key={user.id}
                className={`grid ${GRID_COLUMNS} items-center gap-4 border-b border-[rgba(0,60,107,.08)] px-5 py-3 hover:bg-cedi-surface-tint`}
              >
                <div className="flex min-w-0 items-center gap-3">
                  <div
                    className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full font-display text-xs font-bold text-white"
                    style={{ background: `linear-gradient(145deg,${unitColor},#2F4EF8)` }}
                  >
                    {getInitials(user.name)}
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-cedi-navy">{user.name}</div>
                    <div className="truncate text-xs text-cedi-navy-55">{user.email}</div>
                  </div>
                </div>
                <div className="flex min-w-0 items-center gap-2 text-[13px] text-cedi-navy">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: unitColor }} />
                  <span className="truncate">{user.business_unit ?? "—"}</span>
                </div>
                <div>
                  <span
                    className="inline-flex whitespace-nowrap rounded-full px-3 py-1 text-xs font-bold"
                    style={{ backgroundColor: roleConfig.bg, color: roleConfig.fg }}
                  >
                    {roleConfig.label}
                  </span>
                </div>
                <div>
                  <span
                    className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold"
                    style={{ backgroundColor: statusStyle.bg, color: statusStyle.fg }}
                  >
                    <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: statusStyle.fg }} />
                    {status}
                  </span>
                </div>
                <div className="text-[13px] text-cedi-navy-68">{formatLastAccess(user.last_login_at)}</div>
                <div className="flex justify-end gap-1">
                  <button
                    type="button"
                    onClick={() => setDrawer({ user })}
                    aria-label="Editar usuario"
                    title="Editar"
                    className={ICON_BUTTON_CLASS}
                  >
                    <ActionIcon>
                      <path d="M12 20h9" />
                      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z" />
                    </ActionIcon>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleToggleStatus(user)}
                    disabled={isOwnUser && user.is_active}
                    aria-label={toggleLabel}
                    title={toggleLabel}
                    className={`${ICON_BUTTON_CLASS} disabled:cursor-not-allowed disabled:opacity-40`}
                  >
                    <ActionIcon>
                      <path d={user.is_active ? BAN_PATH : CHECK_PATH} />
                    </ActionIcon>
                  </button>
                </div>
              </div>
            );
          })}

          {usersQuery.isLoading ? (
            <div className="p-10 text-center text-sm text-cedi-navy-55">Cargando usuarios…</div>
          ) : null}
          {usersQuery.isError ? (
            <div role="alert" className="p-10 text-center text-sm text-[#B42318]">
              No se pudieron cargar los usuarios.
            </div>
          ) : null}
          {isEmpty ? (
            <div className="p-10 text-center text-sm text-cedi-navy-55">
              No hay usuarios para los filtros seleccionados.
            </div>
          ) : null}
        </div>
      </section>

      {drawer ? (
        <UserDrawer
          key={drawer.user?.id ?? "new"}
          user={drawer.user}
          isOwnUser={Boolean(drawer.user) && drawer.user?.email.toLowerCase() === session.email.toLowerCase()}
          onClose={() => setDrawer(null)}
        />
      ) : null}
    </div>
  );
}
