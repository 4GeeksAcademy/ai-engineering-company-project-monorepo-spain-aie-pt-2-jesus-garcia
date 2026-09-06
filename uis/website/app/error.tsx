"use client";

import { useEffect } from "react";
import Link from "next/link";

export default function Error({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-6 text-center text-slate-100">
      <h1 className="text-5xl font-bold text-white">Ups…</h1>
      <p className="mt-4 max-w-md text-slate-400">
        Algo salió mal al cargar esta página.
      </p>
      <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
        <button
          onClick={unstable_retry}
          className="rounded-lg bg-cyan-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
        >
          Reintentar
        </button>
        <Link
          href="/"
          className="rounded-lg border border-white/20 px-5 py-2.5 text-sm font-medium text-slate-200 transition hover:bg-white/5"
        >
          Volver al inicio
        </Link>
      </div>
    </div>
  );
}
