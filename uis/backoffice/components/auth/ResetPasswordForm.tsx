"use client";

import { useState, type FormEvent } from "react";
import { resetPasswordRequest } from "@/lib/auth-api";
import { useRouter } from "next/navigation";

export function ResetPasswordForm({ initialToken }: { initialToken?: string }) {
  const router = useRouter();
  const [token] = useState(initialToken ?? "");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Las contraseñas no coinciden.");
      return;
    }

    setLoading(true);
    try {
      await resetPasswordRequest(token, password);
      router.push("/login");
    } catch {
      setError("El enlace no es válido o ha expirado.");
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-5">
      <div>
        <label htmlFor="rp-password" className="block text-sm text-slate-200">
          Nueva contraseña
        </label>
        <input
          id="rp-password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={6}
          className="mt-2 w-full rounded-md border border-white/20 bg-slate-900/60 px-3 py-2 text-slate-100 outline-none focus:border-cyan-300"
        />
      </div>

      <div>
        <label htmlFor="rp-confirm" className="block text-sm text-slate-200">
          Confirmar contraseña
        </label>
        <input
          id="rp-confirm"
          type="password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
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
        {loading ? "Restableciendo…" : "Restablecer contraseña"}
      </button>
    </form>
  );
}
