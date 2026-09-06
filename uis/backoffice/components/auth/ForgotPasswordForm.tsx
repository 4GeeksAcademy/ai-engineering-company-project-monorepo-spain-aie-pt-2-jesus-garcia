"use client";

import { useState, type FormEvent } from "react";
import { forgotPasswordRequest } from "@/lib/auth-api";
import Link from "next/link";

export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await forgotPasswordRequest(email);
    } catch {
      // Ignorar errores para no revelar si el email existe
    } finally {
      setLoading(false);
      setSent(true);
    }
  }

  if (sent) {
    return (
      <div className="space-y-5">
        <p className="rounded-md border border-cyan-300/30 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-200">
          Si existe una cuenta con ese email, te hemos enviado un enlace para
          restablecer tu contraseña.
        </p>
        <p className="text-center text-sm text-slate-400">
          <Link
            href="/login"
            className="text-cyan-400 underline hover:text-cyan-300"
          >
            Volver a iniciar sesión
          </Link>
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-5">
      <p className="text-sm text-slate-400">
        Introduce tu email y te enviaremos un enlace para restablecer tu
        contraseña.
      </p>
      <div>
        <label htmlFor="fp-email" className="block text-sm text-slate-200">
          Email
        </label>
        <input
          id="fp-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          className="mt-2 w-full rounded-md border border-white/20 bg-slate-900/60 px-3 py-2 text-slate-100 outline-none focus:border-cyan-300"
        />
      </div>

      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-md bg-cyan-400 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:opacity-50"
      >
        {loading ? "Enviando…" : "Enviar enlace"}
      </button>

      <p className="text-center text-sm text-slate-400">
        ¿Recordaste tu contraseña?{" "}
        <Link
          href="/login"
          className="text-cyan-400 underline hover:text-cyan-300"
        >
          Inicia sesión
        </Link>
      </p>
    </form>
  );
}
