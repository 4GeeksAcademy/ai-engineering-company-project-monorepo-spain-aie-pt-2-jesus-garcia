"use client";

import { useRef, useState } from "react";
import { friendlyError, uploadRfp } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

interface UploadResult {
  file: string;
  ok: boolean;
  message: string;
}

export function RfpUploader({ onUploaded }: { onUploaded: () => void }) {
  const { token } = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<UploadResult[]>([]);

  async function uploadFiles(files: File[]) {
    if (!files.length) return;
    setBusy(true);
    setResults([]);
    const next: UploadResult[] = [];
    for (const file of files) {
      const looksPdf =
        file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
      if (!looksPdf) {
        next.push({
          file: file.name,
          ok: false,
          message: "Solo se aceptan archivos PDF.",
        });
        continue;
      }
      try {
        const response = await uploadRfp(file, token);
        next.push({
          file: file.name,
          ok: true,
          message: `Ticket ${response.rfp_id} creado y en análisis.`,
        });
      } catch (err) {
        next.push({ file: file.name, ok: false, message: friendlyError(err) });
      }
    }
    setResults(next);
    setBusy(false);
    onUploaded();
  }

  function handleInput(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    void uploadFiles(files);
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    void uploadFiles(Array.from(event.dataTransfer.files));
  }

  return (
    <section className="rounded-xl border border-white/10 bg-slate-900/60 p-5">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-10 text-center transition ${
          dragging
            ? "border-cyan-400 bg-cyan-500/10"
            : "border-white/15 bg-slate-950/40"
        }`}
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          fill="none"
          strokeWidth={1.5}
          stroke="currentColor"
          className="size-10 text-cyan-300"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 7.5 7.5 12M12 7.5V21"
          />
        </svg>
        <div>
          <p className="text-sm font-semibold text-white">
            Arrastra una o varias RFPs en PDF
          </p>
          <p className="mt-1 text-xs text-slate-300">
            Cada PDF crea un ticket independiente y se analiza en segundo plano.
          </p>
        </div>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="rounded-md bg-cyan-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-cyan-600 disabled:opacity-50"
        >
          {busy ? "Subiendo…" : "Seleccionar PDFs"}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          className="hidden"
          onChange={handleInput}
          aria-label="Subir RFPs en PDF"
        />
      </div>

      {results.length > 0 && (
        <ul className="mt-4 space-y-2" aria-live="polite">
          {results.map((result) => (
            <li
              key={`${result.file}-${result.message}`}
              className={`rounded-md border px-3 py-2 text-xs ${
                result.ok
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                  : "border-rose-500/30 bg-rose-500/10 text-rose-200"
              }`}
            >
              <span className="font-semibold">{result.file}:</span> {result.message}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
