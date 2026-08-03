import { zodResolver } from "@hookform/resolvers/zod";
import { isAxiosError } from "axios";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";

import { Button } from "../components/Button";
import { Input } from "../components/Input";
import { useToast } from "../components/ToastContainer";
import { useRegister } from "../hooks/useRegister";

const REQUIRED_MSG = "Este campo es obligatorio";
const PASSWORD_RULE_MSG = "La contraseña debe tener al menos 8 caracteres y un número";
const PASSWORD_MISMATCH_MSG = "Las contraseñas no coinciden";
const SUCCESS_MSG = "Cuenta creada exitosamente";
const DUPLICATE_EMAIL_MSG = "Este email ya está registrado";

const registerSchema = z
  .object({
    name: z.string().trim().min(1, REQUIRED_MSG),
    email: z
      .string()
      .trim()
      .min(1, REQUIRED_MSG)
      .email("Ingresá un email válido")
      .transform((value) => value.toLowerCase()),
    password: z
      .string()
      .min(1, REQUIRED_MSG)
      .refine((value) => value.length >= 8 && /\d/.test(value), PASSWORD_RULE_MSG),
    confirmPassword: z.string().min(1, REQUIRED_MSG),
  })
  .superRefine(({ password, confirmPassword }, context) => {
    if (password && confirmPassword && password !== confirmPassword) {
      context.addIssue({
        code: "custom",
        path: ["confirmPassword"],
        message: PASSWORD_MISMATCH_MSG,
      });
    }
  });

type RegisterFormValues = z.input<typeof registerSchema>;

function getRegisterErrorMessage(error: unknown): string {
  const backendMessage =
    (error as { response?: { data?: { detail?: { error?: { message?: unknown } } } } })
      ?.response?.data?.detail?.error?.message;
  if (typeof backendMessage === "string") {
    return backendMessage;
  }

  if (!isAxiosError(error)) {
    return "No se pudo crear la cuenta";
  }

  if (error.response?.status === 409) {
    return DUPLICATE_EMAIL_MSG;
  }

  return "No se pudo crear la cuenta";
}

export default function Register() {
  const navigate = useNavigate();
  const { addToast } = useToast();
  const { mutateAsync, isPending } = useRegister();

  const {
    register,
    handleSubmit,
    formState: { errors, isValid },
  } = useForm<RegisterFormValues>({
    mode: "onTouched",
    resolver: zodResolver(registerSchema),
    defaultValues: {
      name: "",
      email: "",
      password: "",
      confirmPassword: "",
    },
  });

  const onSubmit = handleSubmit(async ({ name, email, password }) => {
    try {
      await mutateAsync({ name, email, password });
      addToast("success", SUCCESS_MSG);
      window.setTimeout(() => {
        navigate("/login");
      }, 2000);
    } catch (error) {
      addToast("error", getRegisterErrorMessage(error));
    }
  });

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4">
      <form
        noValidate
        onSubmit={onSubmit}
        className="w-full max-w-md space-y-4 rounded-lg bg-surface p-6 shadow-lg"
      >
        <h1 className="text-2xl font-semibold text-gray-900">Crear cuenta</h1>

        <Input
          id="name"
          label="Nombre"
          autoComplete="name"
          {...register("name")}
          error={errors.name?.message}
        />

        <Input
          id="email"
          label="Email"
          type="email"
          autoComplete="email"
          {...register("email")}
          error={errors.email?.message}
        />

        <Input
          id="password"
          label="Contraseña"
          type="password"
          autoComplete="new-password"
          {...register("password")}
          error={errors.password?.message}
        />

        <Input
          id="confirmPassword"
          label="Confirmar contraseña"
          type="password"
          autoComplete="new-password"
          {...register("confirmPassword")}
          error={errors.confirmPassword?.message}
        />

        <Button type="submit" loading={isPending} className="w-full" disabled={!isValid || isPending}>
          Registrarse
        </Button>

        <p className="text-sm text-gray-700">
          ¿Ya tenés cuenta?{" "}
          <Link to="/login" className="font-medium text-primary hover:underline">
            Iniciar sesión
          </Link>
        </p>
      </form>
    </main>
  );
}
