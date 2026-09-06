"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { Sidebar } from "@/components/Sidebar";

export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated, isLoading, sessionError, retryValidation } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated && !sessionError) {
      router.push("/login");
    }
  }, [isLoading, isAuthenticated, sessionError, router]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-slate-600 border-t-cyan-400" />
      </div>
    );
  }

  if (sessionError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950">
        <div className="mx-4 max-w-md rounded-xl border border-rose-400/20 bg-rose-500/10 p-6 text-center">
          <p className="text-sm font-medium text-rose-300">{sessionError}</p>
          <p className="mt-2 text-sm text-slate-400">
            No se pudo validar tu sesión. Vuelve a intentarlo.
          </p>
          <button
            onClick={retryValidation}
            className="mt-4 rounded-lg bg-rose-500/20 px-4 py-2 text-sm font-medium text-rose-200 transition hover:bg-rose-500/30"
          >
            Reintentar
          </button>
          <button
            onClick={() => router.push("/login")}
            className="mt-3 block w-full text-sm text-slate-400 underline hover:text-slate-200"
          >
            Ir a iniciar sesión
          </button>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) return null;

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto p-6 lg:p-10">{children}</main>
    </div>
  );
}
