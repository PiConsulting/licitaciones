import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { exchangeSsoCode } from "../api/auth";
import { saveSession } from "../auth/session";
import { extractApiError } from "../utils/apiError";

const SSO_ERROR_MESSAGES: Record<string, string> = {
  SSO_CODE_INVALID: "El enlace de inicio de sesión expiró o ya fue usado. Iniciá sesión de nuevo.",
  SSO_CALLBACK_INVALID: "No se pudo completar el inicio de sesión con Microsoft. Probá de nuevo.",
  DOMAIN_NOT_MAPPED: "Tu organización no está habilitada para iniciar sesión.",
  SSO_MISCONFIGURED: "El login con Microsoft no está disponible en este momento.",
};
const DEFAULT_SSO_ERROR_MESSAGE = "No se pudo iniciar sesión. Probá de nuevo.";

function resolveSsoError(caught: unknown): string {
  // El backend arma mensajes específicos según la causa real (ver sso.py,
  // describe_callback_error) -- priorizarlo sobre el mapeo genérico de abajo,
  // que solo cubre como fallback los códigos sin mensaje propio del backend.
  const { code, message } = extractApiError(caught);
  if (message) {
    return message;
  }
  if (code && SSO_ERROR_MESSAGES[code]) {
    return SSO_ERROR_MESSAGES[code];
  }
  return DEFAULT_SSO_ERROR_MESSAGE;
}

export default function SsoCallback() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  // El code de intercambio es de un solo uso: React 18 StrictMode (dev) invoca este
  // efecto dos veces al montar, y sin este guard la 2da llamada siempre pega 410.
  const exchangedRef = useRef(false);

  useEffect(() => {
    const code = searchParams.get("code");
    if (!code) {
      setError("Falta el código de inicio de sesión.");
      return;
    }
    if (exchangedRef.current) {
      return;
    }
    exchangedRef.current = true;

    // Sin cleanup/"cancelled": el guard de arriba ya garantiza que este closure es el
    // único que llega a ejecutarse, así que su resultado siempre debe aplicarse.
    exchangeSsoCode(code)
      .then((response) => {
        localStorage.setItem("access_token", response.access_token);
        saveSession({
          name: response.name,
          email: response.email,
          role: response.role,
          business_unit: response.business_unit,
        });
        navigate("/");
      })
      .catch((caught) => {
        setError(resolveSsoError(caught));
      });
  }, [searchParams, navigate]);

  if (error) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-background px-4">
        <div className="w-full max-w-md space-y-4 rounded-lg bg-surface p-6 text-center shadow-lg">
          <p role="alert" className="text-sm text-error">
            {error}
          </p>
          <Link to="/login" className="font-medium text-primary hover:underline">
            Volver a iniciar sesión
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4">
      <p className="text-sm text-gray-700">Completando inicio de sesión…</p>
    </main>
  );
}
