"use client";

import { useMemo, useState } from "react";
import {
  ApiRequestError,
  friendlyError,
  submitRfpApproval,
} from "@/lib/api";
import {
  DEPARTMENT_LABELS,
  RFP_APPROVAL_STATUS_LABELS,
  RFP_APPROVAL_STATUS_STYLES,
  type RfpApprovalAction,
  type RfpApprovalPacket,
  type RfpApprovals,
  type RfpEvaluationResult,
} from "@/lib/rfp-types";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

function errorMessage(err: unknown): string {
  if (err instanceof ApiRequestError && typeof err.detail === "string") {
    return err.detail;
  }
  return friendlyError(err);
}

function Criterion({
  label,
  criterion,
}: {
  label: string;
  criterion?: { pass?: boolean; score?: number; missing_aspects?: string[]; violations?: Array<{ rule_id: string; message: string }> };
}) {
  if (!criterion) return null;
  const pass = criterion.pass !== false;
  return (
    <div
      className={`rounded-lg border p-2 text-xs ${
        pass
          ? "border-emerald-500/25 bg-emerald-500/5 text-emerald-200"
          : "border-rose-500/25 bg-rose-500/5 text-rose-200"
      }`}
    >
      <p className="flex items-center justify-between font-semibold uppercase tracking-wide">
        <span>{label}</span>
        <span>{pass ? "OK" : "Falla"}</span>
      </p>
      {typeof criterion.score === "number" && (
        <p className="mt-1 text-slate-300">Score {criterion.score}</p>
      )}
      {criterion.missing_aspects?.length ? (
        <ul className="mt-1 list-disc pl-4">
          {criterion.missing_aspects.map((aspect) => (
            <li key={aspect}>{aspect}</li>
          ))}
        </ul>
      ) : null}
      {criterion.violations?.length ? (
        <ul className="mt-1 space-y-1">
          {criterion.violations.map((violation, index) => (
            <li key={`${violation.rule_id}-${index}`}>
              <span className="font-semibold">{violation.rule_id}</span>:{" "}
              {violation.message}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function PacketCard({
  item,
  token,
  ticketId,
  onSubmitted,
}: {
  item: RfpApprovalPacket;
  token: string | null;
  ticketId: string;
  onSubmitted: () => void;
}) {
  const packet = item.packet;
  const evaluation = packet.evaluation as RfpEvaluationResult | undefined;
  const [approver, setApprover] = useState(item.responsible ?? "");
  const [comment, setComment] = useState("");
  const [acknowledge, setAcknowledge] = useState(false);
  const [submitting, setSubmitting] = useState<RfpApprovalAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<RfpApprovalAction | null>(null);

  const allowed = packet.allowed_actions ?? [
    "approve",
    "reject",
    "request_changes",
  ];
  const provisional = item.provisional;
  const roundLabel = `${item.approval_round + 1}/${packet.max_rounds ?? "?"}`;

  function validate(action: RfpApprovalAction): string | null {
    if (!approver.trim()) return "Indica el nombre del aprobador.";
    if (action !== "approve" && !comment.trim()) {
      return "Rechazar o solicitar cambios exige un comentario.";
    }
    if (action === "approve" && provisional && !acknowledge) {
      return "La sección es provisional: marca la casilla de aceptación.";
    }
    if (action === "approve" && provisional && !comment.trim()) {
      return "Aprobar una sección provisional exige un comentario.";
    }
    return null;
  }

  async function send(action: RfpApprovalAction) {
    const validation = validate(action);
    if (validation) {
      setError(validation);
      setConfirm(null);
      return;
    }
    if (!item.interrupt_id) {
      setError("La aprobación no tiene interrupt_id; recarga la página.");
      setConfirm(null);
      return;
    }
    setSubmitting(action);
    setError(null);
    try {
      await submitRfpApproval(
        ticketId,
        item.department_id,
        {
          action,
          approver: approver.trim(),
          comment: comment.trim() || null,
          interrupt_id: item.interrupt_id,
          acknowledge_provisional: acknowledge,
        },
        token,
      );
      setComment("");
      setAcknowledge(false);
      setConfirm(null);
      onSubmitted();
    } catch (err) {
      setError(errorMessage(err));
      setConfirm(null);
    } finally {
      setSubmitting(null);
    }
  }

  function request(action: RfpApprovalAction) {
    const validation = validate(action);
    if (validation) {
      setError(validation);
      return;
    }
    if (action === "approve") {
      send("approve");
      return;
    }
    setConfirm(action);
  }

  return (
    <article className="rounded-xl border border-white/10 bg-slate-900/60 p-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-white">
            {DEPARTMENT_LABELS[item.department_id] ??
              item.department_label ??
              item.department_id}
          </h3>
          <p className="text-xs text-slate-400">
            Aprobador: {item.responsible ?? "—"} · Ronda {roundLabel}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {provisional && (
            <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-200">
              Borrador provisional
            </span>
          )}
          <span
            className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${
              RFP_APPROVAL_STATUS_STYLES[
                item.approval_status ?? "pending_approval"
              ] ?? RFP_APPROVAL_STATUS_STYLES.pending_approval
            }`}
          >
            {RFP_APPROVAL_STATUS_LABELS[
              item.approval_status ?? "pending_approval"
            ] ?? item.approval_status}
          </span>
        </div>
      </header>

      <div className="mt-4 grid gap-2 text-xs text-slate-300 sm:grid-cols-2 lg:grid-cols-4">
        <p>
          <span className="text-slate-500">Cliente:</span>{" "}
          {String(packet.client?.name ?? "—")}
        </p>
        <p>
          <span className="text-slate-500">País:</span>{" "}
          {packet.client_country ?? "—"}
        </p>
        <p>
          <span className="text-slate-500">Moneda:</span>{" "}
          {packet.currency ?? "—"}
        </p>
        <p>
          <span className="text-slate-500">Fecha límite:</span>{" "}
          {packet.deadline ?? "—"}
        </p>
      </div>

      {provisional && packet.open_questions?.length ? (
        <p className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-100">
          Esta sección agotó las iteraciones de la Parte 2. Revisa las preguntas
          abiertas antes de aprobar.
        </p>
      ) : null}

      {evaluation && (
        <div className="mt-4 grid gap-2 md:grid-cols-3">
          <Criterion label="Legibilidad" criterion={evaluation.readability} />
          <Criterion label="Pertinencia" criterion={evaluation.relevance} />
          <Criterion label="Cumplimiento" criterion={evaluation.compliance} />
        </div>
      )}

      {Array.isArray(packet.conflicts) && packet.conflicts.length > 0 && (
        <div className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-100">
          <p className="font-semibold">Conflictos arbitrados</p>
          <ul className="mt-1 list-disc pl-4">
            {packet.conflicts.map((conflict, index) => (
              <li key={`${String(conflict.trigger_id)}-${index}`}>
                {String(conflict.trigger_id)} ·{" "}
                {String(conflict.arbitrator ?? "árbitro")}
              </li>
            ))}
          </ul>
        </div>
      )}

      <details className="mt-4 rounded-lg border border-white/10 bg-slate-950/40 p-3" open>
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-cyan-200">
          Contenido de la sección
        </summary>
        <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap text-xs text-slate-200">
          {packet.section_markdown ||
            item.packet.section_markdown ||
            "Sin borrador disponible."}
        </pre>
      </details>

      {packet.open_questions?.length ? (
        <details className="mt-3 rounded-lg border border-white/10 bg-slate-950/40 p-3">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-amber-200">
            Preguntas abiertas ({packet.open_questions.length})
          </summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-amber-100">
            {packet.open_questions.map((question) => (
              <li key={question}>{question}</li>
            ))}
          </ul>
        </details>
      ) : null}

      {error && (
        <p className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-200">
          {error}
        </p>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <label className="text-xs text-slate-300">
          Aprueba en nombre de (responsable)
          <input
            value={approver}
            onChange={(event) => setApprover(event.target.value)}
            className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950/60 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500/50"
          />
        </label>
        <label className="text-xs text-slate-300">
          Comentario de la decisión
          <textarea
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            rows={2}
            placeholder={
              provisional
                ? "Obligatorio al aprobar una sección provisional"
                : "Obligatorio para rechazar o solicitar cambios"
            }
            className="mt-1 w-full rounded-lg border border-white/10 bg-slate-950/60 px-3 py-2 text-sm text-white outline-none focus:border-cyan-500/50"
          />
        </label>
      </div>

      {provisional && (
        <label className="mt-3 flex items-start gap-2 text-xs text-amber-100">
          <input
            type="checkbox"
            checked={acknowledge}
            onChange={(event) => setAcknowledge(event.target.checked)}
            className="mt-0.5"
          />
          Acepto explícitamente el borrador provisional y sus preguntas
          abiertas.
        </label>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {allowed.includes("approve") && (
          <button
            type="button"
            onClick={() => request("approve")}
            disabled={submitting !== null}
            className="rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-3 py-2 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-500/25 disabled:opacity-60"
          >
            {submitting === "approve" ? "Aprobando…" : "Aprobar sección"}
          </button>
        )}
        {allowed.includes("request_changes") && (
          <button
            type="button"
            onClick={() => request("request_changes")}
            disabled={submitting !== null}
            className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs font-semibold text-amber-200 transition hover:bg-amber-500/20 disabled:opacity-60"
          >
            {submitting === "request_changes"
              ? "Enviando…"
              : "Solicitar cambios"}
          </button>
        )}
        {allowed.includes("reject") && (
          <button
            type="button"
            onClick={() => request("reject")}
            disabled={submitting !== null}
            className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs font-semibold text-rose-200 transition hover:bg-rose-500/20 disabled:opacity-60"
          >
            {submitting === "reject" ? "Rechazando…" : "Rechazar sección"}
          </button>
        )}
      </div>

      <ConfirmDialog
        open={confirm !== null}
        title={
          confirm === "reject"
            ? "Rechazar la sección"
            : "Solicitar cambios a la sección"
        }
        message={
          confirm === "reject"
            ? "La sección quedará rechazada y no entrará en el documento final. ¿Continuar?"
            : "La sección se regenerará solo para este departamento y volverá a la cola de aprobación. ¿Continuar?"
        }
        confirmLabel={confirm === "reject" ? "Rechazar" : "Solicitar cambios"}
        danger={confirm === "reject"}
        loading={submitting !== null}
        onConfirm={() => confirm && send(confirm)}
        onCancel={() => setConfirm(null)}
      />
    </article>
  );
}

export function ApprovalPanel({
  ticketId,
  token,
  approvals,
  onSubmitted,
}: {
  ticketId: string;
  token: string | null;
  approvals: RfpApprovals;
  onSubmitted: () => void;
}) {
  const pending = useMemo(() => approvals.pending ?? [], [approvals.pending]);
  const decisions = approvals.decisions ?? [];

  if (pending.length === 0 && decisions.length === 0) {
    return null;
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
          Aprobación humana por departamento
        </h2>
        <span className="rounded-full border border-white/10 px-2.5 py-1 text-xs text-slate-300">
          {pending.length} pendiente(s) · {decisions.length} decidida(s) · run{" "}
          {approvals.run}
        </span>
      </div>

      {pending.length > 0 && (
        <div className="rounded-xl border border-teal-500/30 bg-teal-500/10 p-4 text-sm text-teal-100">
          El ticket está en <strong>esperando_aprobación</strong>. Aprobar un
          departamento no bloquea a los demás: cada rama se reanuda por
          separado.
        </div>
      )}

      {pending.map((item) => (
        <PacketCard
          key={`${item.department_id}-${item.approval_round}-${item.interrupt_id ?? "sin-interrupt"}`}
          item={item}
          token={token}
          ticketId={ticketId}
          onSubmitted={onSubmitted}
        />
      ))}

      {decisions.length > 0 && (
        <article className="rounded-xl border border-white/10 bg-slate-900/60 p-5">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
            Decisiones registradas
          </h3>
          <ul className="mt-3 space-y-2">
            {decisions.map((decision) => (
              <li
                key={decision.department_id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/10 bg-slate-950/40 p-3 text-xs"
              >
                <div>
                  <p className="font-semibold text-white">
                    {DEPARTMENT_LABELS[decision.department_id] ??
                      decision.department_label ??
                      decision.department_id}
                  </p>
                  <p className="text-slate-400">
                    {decision.approver ?? "—"} ·{" "}
                    {decision.approved_at
                      ? new Date(decision.approved_at).toLocaleString("es-ES")
                      : "sin fecha"}
                  </p>
                  {decision.comment && (
                    <p className="mt-1 text-slate-300">{decision.comment}</p>
                  )}
                </div>
                <span
                  className={`rounded-full border px-2.5 py-1 font-semibold ${
                    RFP_APPROVAL_STATUS_STYLES[
                      decision.approval_status ?? ""
                    ] ?? RFP_APPROVAL_STATUS_STYLES.pending_approval
                  }`}
                >
                  {RFP_APPROVAL_STATUS_LABELS[
                    decision.approval_status ?? ""
                  ] ?? decision.approval_status}
                </span>
              </li>
            ))}
          </ul>
        </article>
      )}
    </section>
  );
}
