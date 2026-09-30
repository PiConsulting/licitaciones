import { useEffect, useState } from "react";

import { SUPERADMIN_ROLE } from "../config/userRoles";

const KEYS = {
  token: "access_token",
  name: "user_name",
  email: "user_email",
  role: "user_role",
  businessUnit: "user_business_unit",
} as const;

export const SESSION_CHANGED_EVENT = "session:changed";

export interface SessionProfile {
  name?: string | null;
  email?: string | null;
  role?: string | null;
  business_unit?: string | null;
}

export interface SessionSnapshot {
  name: string;
  email: string;
  role: string;
  businessUnit: string;
  isSuperadmin: boolean;
}

function setOrRemove(key: string, value: string | null | undefined): void {
  const normalized = value?.trim();
  if (normalized) {
    localStorage.setItem(key, normalized);
  } else {
    localStorage.removeItem(key);
  }
}

export function saveSession(profile: SessionProfile): void {
  setOrRemove(KEYS.name, profile.name);
  if (profile.email) {
    setOrRemove(KEYS.email, profile.email);
  }
  setOrRemove(KEYS.role, profile.role);
  setOrRemove(KEYS.businessUnit, profile.business_unit);
  window.dispatchEvent(new CustomEvent(SESSION_CHANGED_EVENT));
}

export function clearSession(): void {
  Object.values(KEYS).forEach((key) => localStorage.removeItem(key));
  window.dispatchEvent(new CustomEvent(SESSION_CHANGED_EVENT));
}

export function readSession(): SessionSnapshot {
  const role = localStorage.getItem(KEYS.role)?.trim() ?? "";
  return {
    name: localStorage.getItem(KEYS.name)?.trim() ?? "",
    email: localStorage.getItem(KEYS.email)?.trim() ?? "",
    role,
    businessUnit: localStorage.getItem(KEYS.businessUnit)?.trim() ?? "",
    isSuperadmin: role === SUPERADMIN_ROLE,
  };
}

export function useSession(): SessionSnapshot {
  const [session, setSession] = useState<SessionSnapshot>(readSession);

  useEffect(() => {
    const refresh = () => setSession(readSession());
    window.addEventListener(SESSION_CHANGED_EVENT, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(SESSION_CHANGED_EVENT, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  return session;
}
