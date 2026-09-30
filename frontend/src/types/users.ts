import type { UserRole } from "../config/userRoles";

export interface SystemUser {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  business_unit: string | null;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface CreateUserPayload {
  name: string;
  email: string;
  business_unit: string;
  role: UserRole;
  is_active: boolean;
  password: string;
}

export interface UpdateUserPayload {
  name?: string;
  email?: string;
  business_unit?: string;
  role?: UserRole;
  is_active?: boolean;
  password?: string;
}
