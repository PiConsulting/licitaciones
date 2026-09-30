const MINUTES_PER_DAY = 24 * 60;

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

export function formatLastAccess(value: string | null, now: Date = new Date()): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  const dayDifference = Math.round(
    (startOfDay(now).getTime() - startOfDay(date).getTime()) / (MINUTES_PER_DAY * 60 * 1000),
  );
  const time = `${pad(date.getHours())}:${pad(date.getMinutes())}`;

  if (dayDifference === 0) {
    return `Hoy, ${time}`;
  }
  if (dayDifference === 1) {
    return `Ayer, ${time}`;
  }
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}`;
}

export function getInitials(name: string): string {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0].toUpperCase())
      .join("") || "?"
  );
}

const PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%";
const GENERATED_PASSWORD_LENGTH = 12;

export function generatePassword(): string {
  const values = new Uint32Array(GENERATED_PASSWORD_LENGTH);
  crypto.getRandomValues(values);
  const password = Array.from(values, (value) => PASSWORD_ALPHABET[value % PASSWORD_ALPHABET.length]).join("");
  return /\d/.test(password) ? password : `${password.slice(0, -1)}7`;
}

export const PASSWORD_RULE_MESSAGE = "La contraseña debe tener al menos 8 caracteres y un número";

export function isValidPassword(value: string): boolean {
  return value.length >= 8 && /\d/.test(value);
}
