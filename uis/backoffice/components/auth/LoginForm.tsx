"use client";

import { useState, type FormEvent } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Loader } from "@/components/Loader";
import { ApiRequestError } from "@/lib/api";
import Link from "next/link";
import { useRouter } from "next/navigation";

export function LoginForm() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showLoader, setShowLoader] = useState(false);
  const [success, setSuccess] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    setShowLoader(true);

    try {
      await login(email, password);
      setSuccess(true);
    } catch (err) {
      setShowLoader(false);
      setLoading(false);
      if (err instanceof ApiRequestError && err.status === 401) {
        setError("Credenciales inválidas. Revisa tu email y contraseña.");
      } else {
        setError("Error al conectar con el servidor. Inténtalo de nuevo.");
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
          <label htmlFor="email" className="block text-sm text-slate-200">
            Email
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="mt-2 w-full rounded-md border border-white/20 bg-slate-900/60 px-3 py-2 text-slate-100 outline-none focus:border-cyan-300"
          />
        </div>

        <div>
          <label htmlFor="password" className="block text-sm text-slate-200">
            Contraseña
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
            className="mt-2 w-full rounded-md border border-white/20 bg-slate-900/60 px-3 py-2 text-slate-100 outline-none focus:border-cyan-300"
          />
        </div>

        {error && (
          <p
            role="alert"
            className="rounded-md border border-red-300/30 bg-red-500/10 px-4 py-3 text-sm text-red-200"
          >
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-md bg-cyan-400 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:opacity-50"
        >
          {loading ? "Iniciando sesión…" : "Iniciar sesión"}
        </button>

        <p className="text-center text-sm text-slate-400">
          <Link
            href="/forgot-password"
            className="text-cyan-400 underline hover:text-cyan-300"
          >
            ¿Olvidaste tu contraseña?
          </Link>
        </p>

        <p className="text-center text-sm text-slate-400">
          ¿No tienes cuenta?{" "}
          <Link
            href="/register"
            className="text-cyan-400 underline hover:text-cyan-300"
          >
            Regístrate
          </Link>
        </p>
      </form>
    </>
  );
}
