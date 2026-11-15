"use client";

import { useState } from "react";
import { downloadRfpFinalDocument, friendlyError } from "@/lib/api";
import type { RfpFinalDocument } from "@/lib/rfp-types";

function formatDate(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("es-ES", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

export function FinalDocumentPanel({
  ticketId,
  token,
  document,
}: {
  ticketId: string;
  token: string | null;
  document: RfpFinalDocument;
}) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download() {
    setDownloading(true);
    setError(null);
    try {
      const blob = await downloadRfpFinalDocument(ticketId, token);
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement("a");
      link.href = url;
      link.download = `${ticketId}-propuesta-final.md`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setDownloading(false);
    }
  }

  return (
    <section className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-emerald-200">
            Documento final acordado
          </h2>
          <p className="mt-1 text-xs text-slate-300">
            {document.contract_version} · {document.currency ?? "—"} ·{" "}
            {formatDate(document.generated_at)}
          </p>
        </div>
        <button
          type="button"
          onClick={download}
          disabled={downloading}
          className="rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-3 py-2 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-500/25 disabled:opacity-60"
        >
          {downloading ? "Descargando…" : "Descargar Markdown"}
        </button>
      </header>

      {error && (
        <p className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200">
          {error}
        </p>
      )}

      {document.approved_by.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-xs">
            <thead className="text-slate-400">
              <tr>
                <th className="px-2 py-1">Departamento</th>
                <th className="px-2 py-1">Responsable</th>
                <th className="px-2 py-1">Aprobador</th>
                <th className="px-2 py-1">Fecha</th>
                <th className="px-2 py-1">Comentario</th>
              </tr>
            </thead>
            <tbody className="text-slate-200">
              {document.approved_by.map((approval) => (
                <tr
                  key={approval.department_id}
                  className="border-t border-white/10"
                >
                  <td className="px-2 py-2">{approval.department_label}</td>
                  <td className="px-2 py-2">{approval.responsible}</td>
                  <td className="px-2 py-2">{approval.approver}</td>
                  <td className="px-2 py-2">
                    {formatDate(approval.approved_at)}
                  </td>
                  <td className="px-2 py-2">{approval.comment ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <details className="mt-4 rounded-lg border border-white/10 bg-slate-950/50 p-3" open>
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-emerald-200">
          Documento consolidado ({document.markdown.length} caracteres)
        </summary>
        <pre className="mt-3 max-h-[36rem] overflow-auto whitespace-pre-wrap text-xs text-slate-200">
          {document.markdown}
        </pre>
      </details>
    </section>
  );
}
