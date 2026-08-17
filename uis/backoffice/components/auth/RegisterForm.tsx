"use client";

import { useState, type FormEvent } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Loader } from "@/components/Loader";
import { ApiRequestError } from "@/lib/api";
import Link from "next/link";
import { useRouter } from "next/navigation";

interface FieldError {
  field: string;
  message: string;
}

function parseFieldErrors(detail: unknown): FieldError[] {
  if (Array.isArray(detail)) {
    return detail.map((d: { loc?: string[]; msg?: string }) => ({
      field: d.loc?.[1] ?? "unknown",
      message: d.msg ?? "Error de validación",
    }));
  }
  if (typeof detail === "string") {
    return [{ field: "email", message: detail }];
  }
  return [];
}

export function RegisterForm() {
  const router = useRouter();
  const { register } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldError[]>([]);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showLoader, setShowLoader] = useState(false);
  const [success, setSuccess] = useState(false);

  function getFieldError(field: string): string | undefined {
    return fieldErrors.find((fe) => fe.field === field)?.message;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFieldErrors([]);
    setGeneralError(null);

    if (password !== confirmPassword) {
      setFieldErrors([{ field: "confirmPassword", message: "Las contraseñas no coinciden." }]);
      return;
    }

    setLoading(true);
    setShowLoader(true);

    try {
      await register(email, password);
      setSuccess(true);
    } catch (err) {
      setShowLoader(false);
      setLoading(false);

      if (err instanceof ApiRequestError) {
        if (err.status === 409) {
          setFieldErrors([{ field: "email", message: "Este email ya está registrado." }]);
        } else if (err.status === 422) {
          setFieldErrors(parseFieldErrors(err.detail));
        } else {
          setGeneralError("Error al registrar. Inténtalo de nuevo.");
        }
      } else {
        setGeneralError("Error al conectar con el servidor.");
      }
    }
  }

  return (
    <>
      {showLoader && (
        <Loader
          onComplete={() => {
            setShowLoader(false);
            if (success) router.push("/");
          }}
        />
      )}
      <form onSubmit={handleSubmit} noValidate className="space-y-5">
        <div>
          <label htmlFor="reg-email" className="block text-sm text-slate-200">
            Email
          </label>
          <input
            id="reg-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className={`mt-2 w-full rounded-md border bg-slate-900/60 px-3 py-2 text-slate-100 outline-none focus:border-cyan-300 ${
              getFieldError("email")
                ? "border-red-400"
                : "border-white/20"
            }`}
          />
          {getFieldError("email") && (
            <p className="mt-1 text-xs text-red-400">{getFieldError("email")}</p>
          )}
        </div>

        <div>
          <label htmlFor="reg-password" className="block text-sm text-slate-200">
            Contraseña
          </label>
          <input
            id="reg-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            className={`mt-2 w-full rounded-md border bg-slate-900/60 px-3 py-2 text-slate-100 outline-none focus:border-cyan-300 ${
              getFieldError("password")
                ? "border-red-400"
                : "border-white/20"
            }`}
          />
          {getFieldError("password") && (
            <p className="mt-1 text-xs text-red-400">{getFieldError("password")}</p>
          )}
        </div>

        <div>
          <label htmlFor="reg-confirm" className="block text-sm text-slate-200">
            Confirmar contraseña
          </label>
          <input
            id="reg-confirm"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            minLength={6}
            className={`mt-2 w-full rounded-md border bg-slate-900/60 px-3 py-2 text-slate-100 outline-none focus:border-cyan-300 ${
              getFieldError("confirmPassword")
                ? "border-red-400"
                : "border-white/20"
            }`}
          />
          {getFieldError("confirmPassword") && (
            <p className="mt-1 text-xs text-red-400">
              {getFieldError("confirmPassword")}
            </p>
          )}
        </div>

        {generalError && (
          <p
            role="alert"
            className="rounded-md border border-red-300/30 bg-red-500/10 px-4 py-3 text-sm text-red-200"
          >
            {generalError}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-md bg-cyan-400 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:opacity-50"
        >
          {loading ? "Creando cuenta…" : "Crear cuenta"}
        </button>

        <p className="text-center text-sm text-slate-400">
          ¿Ya tienes cuenta?{" "}
          <Link
            href="/login"
            className="text-cyan-400 underline hover:text-cyan-300"
          >
            Inicia sesión
          </Link>
        </p>
      </form>
    </>
  );
}
