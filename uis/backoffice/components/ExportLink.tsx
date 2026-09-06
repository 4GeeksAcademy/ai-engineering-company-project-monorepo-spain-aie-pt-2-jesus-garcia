"use client";

import { useState } from "react";
import { ApiRequestError, fetchExportCsv } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

export function ExportLink() {
  const { token } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDownload = async () => {
    setLoading(true);
    setError(null);
    try {
      const blob = await fetchExportCsv(token);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "results.csv";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setError(err.message);
      } else {
        setError("No se pudo descargar el CSV.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <button
        onClick={handleDownload}
        disabled={loading}
        className="flex items-center gap-2 rounded-md bg-cyan-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-60"
      >
        {loading ? "Descargando…" : "Descargar último CSV"}
      </button>
      {error && <p className="mt-2 text-sm text-amber-300">{error}</p>}
    </div>
  );
}
