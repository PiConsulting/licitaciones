import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";

import { login } from "../api/auth";
import { API_BASE_URL } from "../api/client";
import { saveSession } from "../auth/session";
import { Button } from "../components/Button";
import { Input } from "../components/Input";

type SsoTenant = "pi" | "cedi";

const SSO_OPTIONS: { tenant: SsoTenant; label: string }[] = [
  { tenant: "pi", label: "Iniciar sesión — PI Consulting" },
  { tenant: "cedi", label: "Iniciar sesión — CEDI" },
];

const INVALID_CREDENTIALS_MSG = "Email o contraseña incorrectos";

function startSsoLogin(tenant: SsoTenant): void {
  window.location.href = `${API_BASE_URL}/auth/sso/${tenant}/login`;
}

function resolvePasswordLoginError(caught: unknown): string {
  const data = (caught as { response?: { data?: { error?: { code?: string; message?: string } } } })
    ?.response?.data;
  if (data?.error?.code === "USER_SUSPENDED" && data.error.message) {
    return data.error.message;
  }
  return INVALID_CREDENTIALS_MSG;
}

export default function Login() {
  const navigate = useNavigate();
  // Fallback temporal con contraseña mientras se termina de habilitar SSO (a remover en Historia 25.4).
  const [showPasswordFallback, setShowPasswordFallback] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handlePasswordSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const response = await login({ email, password });
      localStorage.setItem("access_token", response.access_token);
      saveSession({
        name: response.name,
        email: response.email || email,
        role: response.role,
        business_unit: response.business_unit,
      });
      navigate("/");
    } catch (caught) {
      setError(resolvePasswordLoginError(caught));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md space-y-4 rounded-lg bg-surface p-6 shadow-lg">
        <h1 className="text-2xl font-semibold text-gray-900">Iniciar sesión</h1>

        {showPasswordFallback ? (
          <form onSubmit={handlePasswordSubmit} className="space-y-4">
            <Input
              id="email"
              label="Email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
            <Input
              id="password"
              label="Contraseña"
              type="password"
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />

            {error ? (
              <p role="alert" className="text-sm text-error">
                {error}
              </p>
            ) : null}

            <Button type="submit" loading={loading} className="w-full">
              Ingresar
            </Button>

            <button
              type="button"
              onClick={() => setShowPasswordFallback(false)}
              className="w-full text-center text-xs text-gray-500 hover:underline"
            >
              Volver a iniciar sesión con Microsoft
            </button>
          </form>
        ) : (
          <>
            <p className="text-sm text-gray-700">
              Elegí tu organización para continuar con tu cuenta de Microsoft.
            </p>

            {SSO_OPTIONS.map(({ tenant, label }) => (
              <Button
                key={tenant}
                type="button"
                className="w-full"
                onClick={() => startSsoLogin(tenant)}
              >
                {label}
              </Button>
            ))}

            <button
              type="button"
              onClick={() => setShowPasswordFallback(true)}
              className="w-full text-center text-xs text-gray-500 hover:underline"
            >
              ¿Problemas con Microsoft? Usar login con contraseña (temporal)
            </button>
          </>
        )}
      </div>
    </main>
  );
}

