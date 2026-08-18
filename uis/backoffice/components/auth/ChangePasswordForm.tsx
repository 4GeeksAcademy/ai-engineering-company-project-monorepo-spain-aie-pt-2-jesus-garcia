"use client";

import { useState, type FormEvent } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { changePasswordRequest } from "@/lib/auth-api";
import { ApiRequestError } from "@/lib/api";
import { useRouter } from "next/navigation";

export function ChangePasswordForm() {
  const router = useRouter();
  const { token } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (newPassword !== confirmPassword) {
      setError("Las contraseñas no coinciden.");
      return;
    }

    if (!token) return;

    setLoading(true);
    try {
      await changePasswordRequest(currentPassword, newPassword, token);
      setSuccess(true);
      router.push("/");
    } catch (err) {
      setLoading(false);
      if (err instanceof ApiRequestError && err.status === 400) {
        setError("La contraseña actual es incorrecta.");
      } else {
        setError("Error al cambiar la contraseña. Inténtalo de nuevo.");
      }
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <h1 className="mb-6 text-center text-2xl font-bold text-white">
        Cambiar contraseña
      </h1>
      {success && (
        <p className="mb-4 rounded-md border border-cyan-300/30 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-200">
          Contraseña actualizada correctamente.
        </p>
      )}
      <form onSubmit={handleSubmit} noValidate className="space-y-5">
        <div>
          <label htmlFor="cp-current" className="block text-sm text-slate-200">
            Contraseña actual
          </label>
          <input
            id="cp-current"
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
            className="mt-2 w-full rounded-md border border-white/20 bg-slate-900/60 px-3 py-2 text-slate-100 outline-none focus:border-cyan-300"
          />
        </div>

        <div>
          <label htmlFor="cp-new" className="block text-sm text-slate-200">
            Nueva contraseña
          </label>
          <input
            id="cp-new"
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            minLength={6}
            className="mt-2 w-full rounded-md border border-white/20 bg-slate-900/60 px-3 py-2 text-slate-100 outline-none focus:border-cyan-300"
          />
        </div>

        <div>
          <label htmlFor="cp-confirm" className="block text-sm text-slate-200">
            Confirmar nueva contraseña
          </label>
          <input
            id="cp-confirm"
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
          {loading ? "Guardando…" : "Cambiar contraseña"}
        </button>
      </form>
    </div>
  );
}
