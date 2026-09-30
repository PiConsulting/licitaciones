export const USER_ROLE_CONFIG = {
  superadmin: {
    label: "Superadmin",
    description: "Acceso total al sistema y a todas las unidades de negocio.",
    fg: "#6E2FC9",
    bg: "rgba(169,102,255,.14)",
  },
  miembro: {
    label: "Miembro",
    description: "Sube y analiza pliegos de su unidad de negocio y hace su seguimiento.",
    fg: "#003C6B",
    bg: "rgba(0,60,107,.08)",
  },
} as const;

export type UserRole = keyof typeof USER_ROLE_CONFIG;

export const USER_ROLES = Object.keys(USER_ROLE_CONFIG) as UserRole[];

export const SUPERADMIN_ROLE: UserRole = "superadmin";

export const DEFAULT_USER_ROLE: UserRole = "miembro";

export function getUserRoleLabel(role: string | null | undefined): string {
  if (!role) {
    return "";
  }
  return (USER_ROLE_CONFIG as Record<string, { label: string }>)[role]?.label ?? role;
}
