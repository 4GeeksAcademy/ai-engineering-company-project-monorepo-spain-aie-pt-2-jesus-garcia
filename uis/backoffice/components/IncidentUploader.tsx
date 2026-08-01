"use client";

import { useCallback, useRef, useState } from "react";

interface IncidentUploaderProps {
  onFile: (file: File) => void;
  loading: boolean;
}

export function IncidentUploader({ onFile, loading }: IncidentUploaderProps) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    (files: FileList | null) => {
      if (!files || files.length === 0) return;
      const file = files[0];
      if (file.name.toLowerCase().endsWith(".csv")) {
        onFile(file);
      } else {
        alert("El archivo debe tener extensión .csv");
      }
    },
    [onFile],
  );

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setDragging(false);
      handleFiles(event.dataTransfer.files);
    },
    [handleFiles],
  );

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Subir archivo CSV"
      onClick={() => !loading && inputRef.current?.click()}
      onKeyDown={(event) => {
        if ((event.key === "Enter" || event.key === " ") && !loading) {
          event.preventDefault();
          inputRef.current?.click();
        }
      }}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-10 text-center transition ${
        dragging
          ? "border-cyan-400 bg-cyan-500/10"
          : "border-white/15 bg-white/5 hover:border-cyan-400/50"
      }`}
    >
      <svg className="h-10 w-10 text-slate-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z" />
      </svg>
      <p className="mt-4 text-sm text-slate-300">
        {loading ? "Analizando archivo…" : "Arrastra y suelta tu archivo CSV aquí"}
      </p>
      <p className="mt-1 text-xs text-slate-500">o haz clic para seleccionarlo</p>
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        className="hidden"
        disabled={loading}
        onChange={(event) => handleFiles(event.target.files)}
      />
    </div>
  );
}
