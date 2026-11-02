"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { IncidentUploader } from "@/components/IncidentUploader";
import { InvalidReasonsList } from "@/components/InvalidReasonsList";
import { ExportLink } from "@/components/ExportLink";
import { MetricCard } from "@/components/ui/MetricCard";
import { BreakdownCard } from "@/components/ui/BreakdownCard";
import { analyzeCsv, fetchTaskStatus, friendlyError } from "@/lib/api";
import type { AnalysisResponse, TaskStatus } from "@/lib/types";
import { CATEGORY_LABELS, STATUS_LABELS } from "@/lib/types";
import { useAuth } from "@/contexts/AuthContext";

const POLL_INTERVAL_MS = 1_500;
const POLL_TIMEOUT_MS = 120_000;

const STATUS_LABEL: Record<TaskStatus, string> = {
  pending: "En cola",
  started: "Analizando",
  success: "Completado",
  failure: "Fallido",
};

export default function BackofficePage() {
  const { token } = useAuth();
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const deadlineTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(true);

  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
    if (deadlineTimer.current) {
      clearTimeout(deadlineTimer.current);
      deadlineTimer.current = null;
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      stopPolling();
    };
  }, [stopPolling]);

  const pollTask = useCallback(
    async function poll(taskIdToPoll: string): Promise<void> {
      try {
        const task = await fetchTaskStatus(taskIdToPoll, token);
        if (!mounted.current) return;

        setTaskStatus(task.status);

        if (task.status === "success") {
          stopPolling();
          setResult(task.result as AnalysisResponse);
          setLoading(false);
          return;
        }

        if (task.status === "failure") {
          stopPolling();
          setError(
            typeof task.result === "string"
              ? task.result
              : "La tarea de análisis ha fallado.",
          );
          setLoading(false);
          return;
        }

        pollTimer.current = setTimeout(() => {
          void poll(taskIdToPoll);
        }, POLL_INTERVAL_MS);
      } catch (err) {
        if (!mounted.current) return;
        stopPolling();
        setError(friendlyError(err));
        setLoading(false);
      }
    },
    [stopPolling, token],
  );

  const handleFile = useCallback(
    async (file: File) => {
      stopPolling();
      setLoading(true);
      setError(null);
      setResult(null);
      setTaskId(null);
      setTaskStatus("pending");
      setFileName(file.name);

      try {
        const accepted = await analyzeCsv(file, token);
        if (!mounted.current) return;

        setTaskId(accepted.task_id);
        deadlineTimer.current = setTimeout(() => {
          if (!mounted.current) return;
          stopPolling();
          setError(
            "La tarea está tardando más de lo esperado. Inténtalo de nuevo.",
          );
          setLoading(false);
        }, POLL_TIMEOUT_MS);

        await pollTask(accepted.task_id);
      } catch (err) {
        if (!mounted.current) return;
        setError(friendlyError(err));
        setTaskStatus(null);
        setLoading(false);
      }
    },
    [pollTask, stopPolling, token],
  );

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
        <div className="mt-4 space-y-1 text-sm text-slate-400">
          <p>
            {taskStatus ? STATUS_LABEL[taskStatus] : "En cola"}{" "}
            <span className="font-medium text-slate-200">{fileName}</span>…
          </p>
          {taskId && (
            <p className="font-mono text-xs text-slate-500">
              task_id: {taskId}
            </p>
          )}
        </div>
      )}

      {error && (
        <div className="mt-6 rounded-xl border border-rose-400/20 bg-rose-500/10 p-5">
          <p className="text-sm font-medium text-rose-300">Error: {error}</p>
          {taskId && (
            <p className="mt-2 font-mono text-xs text-slate-500">
              task_id: {taskId}
            </p>
          )}
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
            {taskId && <ExportLink taskId={taskId} />}
            <div>
              <p className="text-sm text-slate-500">
                Último análisis: {fileName}
              </p>
              {taskId && (
                <p className="font-mono text-xs text-slate-500">
                  task_id: {taskId}
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
