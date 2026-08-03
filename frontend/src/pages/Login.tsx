import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { login } from "../api/auth";
import { Button } from "../components/Button";
import { Input } from "../components/Input";

const INVALID_CREDENTIALS_MSG = "Email o contraseña incorrectos";

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const response = await login({ email, password });
      localStorage.setItem("access_token", response.access_token);
      navigate("/dashboard");
    } catch {
      setError(INVALID_CREDENTIALS_MSG);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md space-y-4 rounded-lg bg-surface p-6 shadow-lg"
      >
        <h1 className="text-2xl font-semibold text-gray-900">Iniciar sesión</h1>
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

        {error ? <p role="alert" className="text-sm text-error">{error}</p> : null}

        <Button type="submit" loading={loading} className="w-full">
          Ingresar
        </Button>

        <p className="text-sm text-gray-700">
          ¿No tenés cuenta?{" "}
          <Link to="/register" className="font-medium text-primary hover:underline">
            Registrate
          </Link>
        </p>
      </form>
    </main>
  );
}
