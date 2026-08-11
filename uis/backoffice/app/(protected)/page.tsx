"use client";

import { useCallback, useState } from "react";
import { IncidentUploader } from "@/components/IncidentUploader";
import { InvalidReasonsList } from "@/components/InvalidReasonsList";
import { ExportLink } from "@/components/ExportLink";
import { MetricCard } from "@/components/ui/MetricCard";
import { BreakdownCard } from "@/components/ui/BreakdownCard";
import { analyzeCsv, ApiRequestError } from "@/lib/api";
import type { AnalysisResponse } from "@/lib/types";
import { CATEGORY_LABELS, STATUS_LABELS } from "@/lib/types";

export default function BackofficePage() {
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback(async (file: File) => {
    setLoading(true);
    setError(null);
    setResult(null);
    setFileName(file.name);
    try {
      const data = await analyzeCsv(file);
      setResult(data);
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setError(err.message);
      } else {
        setError("No se pudo analizar el archivo.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">
          Análisis de incidentes
        </h1>
        <p className="mt-2 text-slate-400">
          Sube un CSV del departamento de Experiencia del cliente para
          obtener métricas, desgloses y el índice de satisfacción.
        </p>
      </div>

      <IncidentUploader onFile={handleFile} loading={loading} />

      {fileName && !result && !error && (
        <p className="mt-4 text-sm text-slate-400">
          Analizando <span className="font-medium text-slate-200">{fileName}</span>…
        </p>
      )}

      {error && (
        <div className="mt-6 rounded-xl border border-rose-400/20 bg-rose-500/10 p-5">
          <p className="text-sm font-medium text-rose-300">Error: {error}</p>
        </div>
      )}

      {result && (
        <div className="mt-8 space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard title="Total procesados" value={result.total} />
            <MetricCard title="Registros válidos" value={result.valid} />
            <MetricCard title="Registros inválidos" value={result.invalid} />
            <MetricCard
              title="Satisfacción media (cerrados)"
              value={
                result.avg_satisfaction_cerrados !== null
                  ? result.avg_satisfaction_cerrados.toFixed(2)
                  : "n/d"
              }
              subtitle="Escala 0-10"
            />
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            <BreakdownCard
              title="Por estado"
              items={result.by_status}
              labels={STATUS_LABELS}
            />
            <BreakdownCard
              title="Por categoría"
              items={result.by_category}
              labels={CATEGORY_LABELS}
            />
          </div>

          <InvalidReasonsList reasons={result.invalid_reasons} />

          <div className="flex items-center gap-4">
            <ExportLink />
            <p className="text-sm text-slate-500">
              Último análisis: {fileName}
            </p>
          </div>
        </div>
      )}
    </>
  );
}
