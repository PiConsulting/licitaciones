import { Eye, X } from "lucide-react";
import { useState } from "react";

import { useToast } from "../../components/ToastContainer";
import { BUSINESS_UNITS, DEFAULT_BUSINESS_UNIT } from "../../config/businessUnits";
import {
  DEFAULT_USER_ROLE,
  SUPERADMIN_ROLE,
  USER_ROLE_CONFIG,
  USER_ROLES,
  type UserRole,
} from "../../config/userRoles";
import type { SystemUser } from "../../types/users";
import { useCreateUserMutation, useUpdateUserMutation } from "./hooks/useUsers";
import { generatePassword, isValidPassword, PASSWORD_RULE_MESSAGE } from "./userFormatting";

interface UserFormState {
  name: string;
  email: string;
  businessUnit: string;
  role: UserRole;
  isActive: boolean;
  password: string;
}

interface UserDrawerProps {
  user: SystemUser | null;
  isOwnUser: boolean;
  onClose: () => void;
}

const LABEL_CLASS = "text-xs font-bold uppercase tracking-[.14em] text-cedi-navy-55";
const FIELD_CLASS =
  "h-11 rounded-full border-[1.5px] border-cedi-navy-20 bg-white px-[18px] text-sm text-cedi-navy focus:border-cedi-celeste focus:outline-none focus:ring-0 disabled:cursor-not-allowed disabled:opacity-60";
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const GENERIC_SAVE_ERROR = "No se pudo guardar el usuario";

function buildInitialForm(user: SystemUser | null): UserFormState {
  if (!user) {
    return {
      name: "",
      email: "",
      businessUnit: DEFAULT_BUSINESS_UNIT,
      role: DEFAULT_USER_ROLE,
      isActive: true,
      password: "",
    };
  }
  return {
    name: user.name,
    email: user.email,
    businessUnit: user.business_unit ?? DEFAULT_BUSINESS_UNIT,
    role: user.role,
    isActive: user.is_active,
    password: "",
  };
}

function extractErrorMessage(error: unknown): string {
  const data = (error as { response?: { data?: { error?: { message?: string }; detail?: unknown } } })
    ?.response?.data;
  if (data?.error?.message) {
    return data.error.message;
  }
  if (Array.isArray(data?.detail)) {
    const first = data.detail[0] as { msg?: string } | undefined;
    if (first?.msg) {
      return first.msg.replace(/^Value error, /, "");
    }
  }
  return GENERIC_SAVE_ERROR;
}

export function UserDrawer({ user, isOwnUser, onClose }: UserDrawerProps) {
  const isNew = user === null;
  const [form, setForm] = useState<UserFormState>(() => buildInitialForm(user));
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const createMutation = useCreateUserMutation();
  const updateMutation = useUpdateUserMutation();
  const { addToast } = useToast();
  const isSaving = createMutation.isPending || updateMutation.isPending;

  const title = isNew ? "Nuevo usuario" : "Editar usuario";
  const subtitle = isNew ? "Se da de alta en la unidad elegida." : "Los cambios se aplican al guardar.";
  const passwordLabel = isNew ? "Contraseña temporal" : "Nueva contraseña (opcional)";
  const passwordPlaceholder = isNew ? "Asignale una contraseña" : "Dejar vacío para no cambiarla";
  const passwordHint = isNew
    ? "La persona podrá cambiarla cuando ingrese."
    : "Si la cambiás, se le pedirá una nueva al ingresar.";

  function patch(values: Partial<UserFormState>) {
    setForm((current) => ({ ...current, ...values }));
  }

  function validate(): string | null {
    if (!form.name.trim()) {
      return "Ingresá el nombre completo";
    }
    if (!EMAIL_PATTERN.test(form.email.trim())) {
      return "Ingresá un email válido";
    }
    if (isNew && !form.password) {
      return "Asignale una contraseña al usuario";
    }
    if (form.password && !isValidPassword(form.password)) {
      return PASSWORD_RULE_MESSAGE;
    }
    return null;
  }

  async function handleSave() {
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);

    try {
      if (isNew) {
        await createMutation.mutateAsync({
          name: form.name.trim(),
          email: form.email.trim(),
          business_unit: form.businessUnit,
          role: form.role,
          is_active: form.isActive,
          password: form.password,
        });
      } else {
        await updateMutation.mutateAsync({
          userId: user.id,
          payload: {
            name: form.name.trim(),
            email: form.email.trim(),
            business_unit: form.businessUnit,
            role: form.role,
            is_active: form.isActive,
            ...(form.password ? { password: form.password } : {}),
          },
        });
      }
      addToast("success", isNew ? `Usuario ${form.name.trim()} creado.` : `Usuario ${form.name.trim()} actualizado.`);
      onClose();
    } catch (caught) {
      const message = extractErrorMessage(caught);
      setError(message);
      addToast("error", message);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-[rgba(0,60,107,.35)]" onClick={onClose} aria-hidden="true" />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="relative flex h-full w-full max-w-[440px] flex-col bg-white leading-[normal] shadow-[-12px_0_32px_rgba(0,60,107,.18)]"
      >
        <div className="flex items-start justify-between gap-3 border-b border-cedi-navy-12 px-6 pb-4 pt-6">
          <div>
            <h2 className="m-0 font-display text-[22px] font-bold leading-[1.2] tracking-[-0.015em] text-cedi-navy">
              {title}
            </h2>
            <p className="m-0 mt-1 text-[13px] leading-normal text-cedi-navy-68">{subtitle}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border-0 bg-transparent text-cedi-navy-68 hover:bg-[rgba(0,60,107,.08)] hover:text-cedi-navy"
          >
            <X size={18} strokeWidth={2.2} aria-hidden="true" />
          </button>
        </div>

        <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-6 py-5">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="u-name" className={LABEL_CLASS}>
              Nombre completo
            </label>
            <input
              id="u-name"
              type="text"
              value={form.name}
              onChange={(event) => patch({ name: event.target.value })}
              placeholder="Ej: Lucía Benítez"
              className={FIELD_CLASS}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="u-email" className={LABEL_CLASS}>
              Email
            </label>
            <input
              id="u-email"
              type="email"
              value={form.email}
              onChange={(event) => patch({ email: event.target.value })}
              placeholder="nombre@empresa.com"
              className={FIELD_CLASS}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="u-unit" className={LABEL_CLASS}>
              Unidad de negocio
            </label>
            <select
              id="u-unit"
              value={form.businessUnit}
              onChange={(event) => patch({ businessUnit: event.target.value })}
              className={FIELD_CLASS}
            >
              {BUSINESS_UNITS.map((unit) => (
                <option key={unit} value={unit}>
                  {unit}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-2">
            <span className={LABEL_CLASS}>Rol</span>
            <div role="radiogroup" aria-label="Rol" className="flex flex-col gap-2">
              {USER_ROLES.map((role) => {
                const active = form.role === role;
                const locked = isOwnUser && role !== SUPERADMIN_ROLE;
                return (
                  <button
                    key={role}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    disabled={locked}
                    onClick={() => patch({ role })}
                    className={[
                      "flex items-start gap-3 rounded-xl border-[1.5px] px-3.5 py-2.5 text-left text-cedi-navy disabled:cursor-not-allowed disabled:opacity-60",
                      active
                        ? "border-cedi-celeste bg-[rgba(0,153,219,.06)]"
                        : "border-cedi-navy-20 bg-white hover:border-cedi-celeste",
                    ].join(" ")}
                  >
                    <span
                      className={[
                        "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-[1.5px]",
                        active ? "border-cedi-celeste" : "border-cedi-navy-30",
                      ].join(" ")}
                    >
                      <span
                        className={["h-2 w-2 rounded-full", active ? "bg-cedi-celeste" : "bg-transparent"].join(" ")}
                      />
                    </span>
                    <span className="flex flex-col gap-0.5">
                      <span className="text-[13px] font-bold">{USER_ROLE_CONFIG[role].label}</span>
                      <span className="text-xs leading-[1.4] text-cedi-navy-68">
                        {USER_ROLE_CONFIG[role].description}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="u-status" className={LABEL_CLASS}>
              Estado
            </label>
            <select
              id="u-status"
              value={form.isActive ? "Activo" : "Suspendido"}
              disabled={isOwnUser}
              onChange={(event) => patch({ isActive: event.target.value === "Activo" })}
              className={FIELD_CLASS}
            >
              <option value="Activo">Activo</option>
              <option value="Suspendido">Suspendido</option>
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="u-pass" className={LABEL_CLASS}>
              {passwordLabel}
            </label>
            <div className="flex h-11 items-center rounded-full border-[1.5px] border-cedi-navy-20 bg-white pl-[18px] pr-1.5 focus-within:border-cedi-celeste">
              <input
                id="u-pass"
                type={showPassword ? "text" : "password"}
                value={form.password}
                onChange={(event) => patch({ password: event.target.value })}
                placeholder={passwordPlaceholder}
                autoComplete="new-password"
                className="min-w-0 flex-1 border-0 bg-transparent p-0 text-sm text-cedi-navy outline-none focus:ring-0"
              />
              <button
                type="button"
                onClick={() => setShowPassword((current) => !current)}
                aria-label="Mostrar u ocultar contraseña"
                title="Mostrar u ocultar"
                className="inline-flex h-8 w-8 items-center justify-center rounded-full border-0 bg-transparent text-cedi-navy-55 hover:bg-cedi-surface-tint hover:text-cedi-navy"
              >
                <Eye size={16} strokeWidth={2} aria-hidden="true" />
              </button>
              <button
                type="button"
                onClick={() => {
                  patch({ password: generatePassword() });
                  setShowPassword(true);
                }}
                className="inline-flex h-8 items-center gap-1.5 rounded-full border-0 bg-cedi-surface-tint px-3 text-xs font-semibold text-cedi-navy hover:bg-[rgba(0,60,107,.08)]"
              >
                Generar
              </button>
            </div>
            <span className="text-xs leading-normal text-cedi-navy-55">{passwordHint}</span>
          </div>

          {error ? (
            <p role="alert" className="m-0 text-[13px] font-semibold text-[#B42318]">
              {error}
            </p>
          ) : null}
        </div>

        <div className="flex justify-end gap-2 border-t border-cedi-navy-12 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-10 items-center rounded-full border-[1.5px] border-cedi-navy-20 bg-white px-[18px] text-[13px] font-semibold text-cedi-navy hover:border-cedi-celeste"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={isSaving}
            className="inline-flex h-10 items-center rounded-full border-0 bg-gradient-to-r from-[#2F4EF8] to-[#A966FF] px-5 text-[13px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isNew ? "Crear usuario" : "Guardar cambios"}
          </button>
        </div>
      </aside>
    </div>
  );
}
