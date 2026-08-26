"use client";

import { useEffect } from "react";

export default function GlobalError({
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
    <html>
      <body className="bg-slate-950 text-slate-100 antialiased">
        <div className="flex min-h-screen flex-col items-center justify-center px-6 text-center">
          <h1 className="text-5xl font-bold text-white">Ups…</h1>
          <p className="mt-4 max-w-md text-slate-400">
            Ha ocurrido un error inesperado. Vuelve a intentarlo.
          </p>
          <button
            onClick={unstable_retry}
            className="mt-8 rounded-lg bg-cyan-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
          >
            Reintentar
          </button>
        </div>
      </body>
    </html>
  );
}
