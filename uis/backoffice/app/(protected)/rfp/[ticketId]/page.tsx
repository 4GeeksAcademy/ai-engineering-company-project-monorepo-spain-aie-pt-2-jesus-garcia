"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  fetchRfpApprovals,
  fetchRfpFinalDocument,
  fetchRfpTicket,
  fetchRfpTrace,
  friendlyError,
  startRfpApprovals,
  startRfpProposal,
} from "@/lib/api";
import {
  DEPARTMENT_LABELS,
  RFP_POLLING_STATUSES,
  SERVICE_LABELS,
  formatRfpDate,
  type RfpApprovals,
  type RfpFinalDocument,
  type RfpTicketDetail,
  type RfpTrace,
} from "@/lib/rfp-types";
import { useAsyncData } from "@/hooks/useAsyncData";
import { useAuth } from "@/contexts/AuthContext";
import { RfpStatusBadge } from "@/components/rfp/RfpStatusBadge";
import { ProposalSectionCard } from "@/components/rfp/ProposalSectionCard";
import { ApprovalPanel } from "@/components/rfp/ApprovalPanel";
import { FinalDocumentPanel } from "@/components/rfp/FinalDocumentPanel";
import { TraceTimeline } from "@/components/rfp/TraceTimeline";

interface RfpPageData {
  ticket: RfpTicketDetail;
  approvals: RfpApprovals;
  trace: RfpTrace;
  finalDocument: RfpFinalDocument | null;
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-white/10 bg-slate-950/40 p-3">
      <p className="text-[11px] uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-sm font-semibold text-white">{value}</p>
    </div>
  );
}

function emptyApprovals(ticket: RfpTicketDetail): RfpApprovals {
  return {
    ticket_id: ticket.ticket_id,
    rfp_id: ticket.rfp_id,
    status: ticket.status,
    approval_status: ticket.approval_status,
    thread_id: ticket.approval_thread_id,
    run: 0,
    max_rounds: 2,
    pending: [],
    decisions: [],
    final_document_ready: ticket.final_document_ready,
  };
}

export default function RfpDetailPage() {
  const params = useParams<{ ticketId: string }>();
  const ticketId = Array.isArray(params.ticketId)
    ? params.ticketId[0]
    : params.ticketId;
  const { token } = useAuth();
  const [generating, setGenerating] = useState(false);
  const [startingApprovals, setStartingApprovals] = useState(false);
  const [proposalError, setProposalError] = useState<string | null>(null);
  const [approvalStartError, setApprovalStartError] = useState<string | null>(
    null,
  );

  const { data, loading, error, reload } = useAsyncData<RfpPageData>(
    async () => {
      const ticket = await fetchRfpTicket(ticketId, token);
      let approvals = emptyApprovals(ticket);
      try {
        approvals = await fetchRfpApprovals(ticketId, token);
      } catch {
        approvals = emptyApprovals(ticket);
      }
      let trace: RfpTrace = {
        ticket_id: ticketId,
        events: [],
        arbitrations: [],
      };
      try {
        trace = await fetchRfpTrace(ticketId, token);
      } catch {
        trace = { ticket_id: ticketId, events: [], arbitrations: [] };
      }
      let finalDocument: RfpFinalDocument | null = null;
      if (ticket.final_document_ready) {
        try {
          finalDocument = await fetchRfpFinalDocument(ticketId, token);
        } catch {
          finalDocument = null;
        }
      }
      return { ticket, approvals, trace, finalDocument };
    },
    [ticketId, token],
    friendlyError,
  );

  const ticket = data?.ticket;
  const isPolling =
    !!ticket &&
    (RFP_POLLING_STATUSES.includes(ticket.status) ||
      ticket.proposal_status === "encolado" ||
      ticket.approval_status === "resuming" ||
      ticket.approval_status === "encolado");

  useEffect(() => {
    if (!isPolling) return;
    const timer = window.setInterval(reload, 3000);
    return () => window.clearInterval(timer);
  }, [isPolling, reload]);

  async function handleGenerateProposal() {
    setGenerating(true);
    setProposalError(null);
    try {
      await startRfpProposal(ticketId, token);
      reload();
    } catch (err) {
      setProposalError(friendlyError(err));
    } finally {
      setGenerating(false);
    }
  }

  async function handleStartApprovals() {
    setStartingApprovals(true);
    setApprovalStartError(null);
    try {
      await startRfpApprovals(ticketId, token);
      reload();
    } catch (err) {
      setApprovalStartError(friendlyError(err));
    } finally {
      setStartingApprovals(false);
    }
  }

  if (loading && !data) {
    return <p className="text-sm text-slate-400">Cargando ticket…</p>;
  }

  if (error || !ticket || !data) {
    return (
      <div className="space-y-4">
        <Link href="/rfp" className="text-sm text-cyan-300 hover:text-cyan-200">
          ← Volver a recepción de RFPs
        </Link>
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
          {error ?? "Ticket no encontrado."}
        </p>
      </div>
    );
  }

  const metadata = ticket.metadata;
  const readability = metadata?.readability_metrics ?? {};
  const classification = ticket.classification ?? {};
  const handoff = ticket.handoff;
  const approvalActive = ["pending", "resuming", "encolado"].includes(
    ticket.approval_status ?? "",
  );
  const canGenerateProposal =
    ticket.handoff_status === "ready" &&
    ["analisis_completo", "needs_human_review", "esperando_aprobación"].includes(
      ticket.status,
    ) &&
    !approvalActive &&
    ticket.status !== "terminado";
  const hasProposalSections = ticket.sections.some(
    (section) => section.draft_content || section.evaluation_results,
  );
  const canStartApprovals =
    ["esperando_aprobación", "needs_human_review"].includes(ticket.status) &&
    !["pending", "resuming", "encolado", "rejected"].includes(
      ticket.approval_status ?? "",
    ) &&
    data.approvals.pending.length === 0 &&
    data.approvals.decisions.length === 0;
  const hasApprovals =
    data.approvals.pending.length > 0 ||
    data.approvals.decisions.length > 0 ||
    ticket.status === "esperando_aprobación" ||
    ticket.status === "terminado";

  return (
    <div className="space-y-6">
      <Link href="/rfp" className="text-sm text-cyan-300 hover:text-cyan-200">
        ← Volver a recepción de RFPs
      </Link>

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-bold text-white">{ticket.rfp_id}</h1>
            <RfpStatusBadge status={ticket.status} />
          </div>
          <p className="mt-1 text-sm text-slate-300">
            {metadata?.client_name ?? "Cliente sin identificar"} ·{" "}
            {metadata?.client_country ?? "país por confirmar"} ·{" "}
            {metadata?.currency ?? "moneda por confirmar"}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            {ticket.original_filename} · etapa {ticket.pipeline_stage ?? "—"} ·
            actualizado {formatRfpDate(ticket.updated_at)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isPolling && (
            <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-xs text-cyan-200">
              Actualizando cada 3 s…
            </span>
          )}
          {canStartApprovals && (
            <button
              type="button"
              onClick={handleStartApprovals}
              disabled={startingApprovals}
              className="rounded-lg border border-teal-500/40 bg-teal-500/15 px-3 py-2 text-xs font-semibold text-teal-200 transition hover:bg-teal-500/25 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {startingApprovals ? "Iniciando…" : "Iniciar aprobaciones"}
            </button>
          )}
          {canGenerateProposal && (
            <button
              type="button"
              onClick={handleGenerateProposal}
              disabled={generating}
              className="rounded-lg border border-emerald-500/40 bg-emerald-500/15 px-3 py-2 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-500/25 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {generating
                ? "Encolando…"
                : ticket.proposal_status
                  ? "Regenerar propuesta"
                  : "Generar propuesta"}
            </button>
          )}
        </div>
      </header>

      {ticket.status === "esperando_aprobación" && (
        <div className="rounded-xl border border-teal-500/30 bg-teal-500/10 p-4 text-sm text-teal-100">
          <p className="font-semibold">Aprobación humana pendiente</p>
          <p className="mt-1">
            Cada departamento aprueba su sección por separado. Las ramas ya
            aprobadas no se bloquean entre sí.
          </p>
        </div>
      )}

      {ticket.status === "terminado" && (
        <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-4 text-sm text-emerald-100">
          <p className="font-semibold">Documento final generado</p>
          <p className="mt-1">
            Todas las secciones activas están aprobadas y consolidadas. El
            documento está disponible para Ventas.
          </p>
        </div>
      )}

      {approvalStartError && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
          <p className="font-semibold">No se pudo iniciar la aprobación</p>
          <p className="mt-1">{approvalStartError}</p>
        </div>
      )}

      {proposalError && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
          <p className="font-semibold">No se pudo iniciar la propuesta</p>
          <p className="mt-1">{proposalError}</p>
        </div>
      )}

      {ticket.proposal_error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
          <p className="font-semibold">La generación de la propuesta falló</p>
          <p className="mt-1">{ticket.proposal_error}</p>
        </div>
      )}

      {ticket.approval_error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
          <p className="font-semibold">El flujo de aprobación falló</p>
          <p className="mt-1">{ticket.approval_error}</p>
        </div>
      )}

      {ticket.status === "error" && ticket.error_message && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
          <p className="font-semibold">El pipeline falló</p>
          <p className="mt-1">{ticket.error_message}</p>
        </div>
      )}

      {ticket.status === "descartado" && (
        <div className="rounded-xl border border-slate-500/30 bg-slate-500/10 p-4 text-sm text-slate-200">
          <p className="font-semibold">Documento descartado</p>
          <p className="mt-1">
            {ticket.discard_reason ?? "Sin motivo registrado."}
          </p>
          {typeof classification.reason === "string" && (
            <p className="mt-2 text-xs text-slate-400">
              Clasificador: {String(classification.document_type ?? "—")} ·
              confianza{" "}
              {typeof classification.confidence === "number"
                ? classification.confidence.toFixed(2)
                : "—"}
            </p>
          )}
        </div>
      )}

      {data.finalDocument && (
        <FinalDocumentPanel
          ticketId={ticket.ticket_id}
          token={token}
          document={data.finalDocument}
        />
      )}

      {hasApprovals && (
        <ApprovalPanel
          ticketId={ticket.ticket_id}
          token={token}
          approvals={data.approvals}
          onSubmitted={reload}
        />
      )}

      {metadata && (
        <section className="rounded-xl border border-white/10 bg-slate-900/60 p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
            Metadatos de la RFP
          </h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Cliente" value={metadata.client_name ?? "—"} />
            <Metric label="País" value={metadata.client_country ?? "—"} />
            <Metric label="Moneda" value={metadata.currency ?? "—"} />
            <Metric label="Idioma" value={metadata.language ?? "—"} />
            <Metric
              label="Volumen mensual"
              value={metadata.monthly_volume ?? "No declarado"}
            />
            <Metric
              label="Fecha límite"
              value={metadata.deadline ?? "No declarada"}
            />
            <Metric
              label="Presupuesto"
              value={metadata.budget_range ?? "No declarado"}
            />
            <Metric
              label="Servicios"
              value={
                metadata.services_requested.length
                  ? metadata.services_requested
                      .map((service) => SERVICE_LABELS[service] ?? service)
                      .join(", ")
                  : "—"
              }
            />
          </div>

          {metadata.scope_notes.length > 0 && (
            <div className="mt-4">
              <p className="text-xs uppercase tracking-wide text-slate-400">
                Alcance declarado
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-200">
                {metadata.scope_notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </div>
          )}

          {metadata.unknown_services.length > 0 && (
            <p className="mt-3 text-xs text-amber-300">
              Fuera de catálogo: {metadata.unknown_services.join(", ")}
            </p>
          )}

          {metadata.missing_fields.length > 0 && (
            <p className="mt-2 text-xs text-slate-400">
              Datos no declarados: {metadata.missing_fields.join(", ")}
            </p>
          )}
        </section>
      )}

      {metadata && Object.keys(readability).length > 0 && (
        <section className="rounded-xl border border-white/10 bg-slate-900/60 p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
            Legibilidad y coste de procesamiento
          </h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Palabras" value={String(readability.word_count ?? "—")} />
            <Metric
              label="Tokens estimados"
              value={String(readability.estimated_llm_tokens ?? "—")}
            />
            <Metric
              label="Flesch Reading Ease"
              value={String(readability.flesch_reading_ease ?? "—")}
            />
            <Metric
              label="Nivel Flesch-Kincaid"
              value={String(readability.flesch_kincaid_grade ?? "—")}
            />
            <Metric
              label="Complejidad"
              value={String(readability.complexity_band ?? "—")}
            />
            <Metric
              label="Coste estimado"
              value={String(readability.processing_cost_hint ?? "—")}
            />
            <Metric
              label="Páginas"
              value={String(metadata.document_metadata.page_count ?? "—")}
            />
            <Metric
              label="Conversor"
              value={String(metadata.document_metadata.converter ?? "—")}
            />
          </div>
        </section>
      )}

      {hasProposalSections && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
            Propuesta económica por departamento
          </h2>
          {ticket.sections
            .filter(
              (section) =>
                section.draft_content || section.evaluation_results,
            )
            .map((section) => (
              <ProposalSectionCard
                key={section.department_id}
                section={section}
              />
            ))}
        </section>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
          Aspectos clave por departamento
        </h2>
        {ticket.sections.length === 0 ? (
          <p className="rounded-xl border border-white/10 bg-slate-900/60 p-5 text-sm text-slate-400">
            Todavía no hay secciones departamentales.
          </p>
        ) : (
          ticket.sections.map((section) => (
            <article
              key={section.department_id}
              className="rounded-xl border border-white/10 bg-slate-900/60 p-5"
            >
              <header className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="text-base font-semibold text-white">
                    {DEPARTMENT_LABELS[section.department_id] ??
                      section.department_id}
                  </h3>
                  <p className="text-xs text-slate-400">
                    Responsable: {section.responsible ?? "—"}
                  </p>
                </div>
              </header>

              <ul className="mt-4 space-y-3">
                {section.key_aspects.map((aspect, index) => (
                  <li
                    key={`${section.department_id}-${aspect.aspect}-${index}`}
                    className="rounded-lg border border-white/10 bg-slate-950/40 p-3"
                  >
                    <p className="text-sm font-semibold text-cyan-200">
                      {aspect.aspect}
                    </p>
                    <p className="mt-1 text-sm text-slate-200">{aspect.detail}</p>
                    {aspect.evidence && (
                      <p className="mt-1 text-xs italic text-slate-400">
                        Evidencia: “{aspect.evidence}”
                      </p>
                    )}
                  </li>
                ))}
              </ul>

              {section.open_questions.length > 0 && (
                <div className="mt-4">
                  <p className="text-xs uppercase tracking-wide text-amber-300">
                    Preguntas abiertas
                  </p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-100">
                    {section.open_questions.map((question) => (
                      <li key={question}>{question}</li>
                    ))}
                  </ul>
                </div>
              )}

              {section.unsupported_claims.length > 0 && (
                <p className="mt-3 text-xs text-rose-300">
                  {section.unsupported_claims.length} afirmación(es) descartada(s)
                  por contener cifras no presentes en la RFP.
                </p>
              )}
            </article>
          ))
        )}
      </section>

      {handoff && (
        <section className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-cyan-200">
              Handoff para Ventas
            </h2>
            <span className="rounded-full border border-cyan-500/30 px-2.5 py-1 text-xs text-cyan-200">
              {handoff.contract_version}
            </span>
          </div>
          <p className="mt-3 whitespace-pre-line text-sm text-slate-100">
            {handoff.sales_summary}
          </p>

          {handoff.questions_to_ask.length > 0 && (
            <div className="mt-4">
              <p className="text-xs uppercase tracking-wide text-cyan-200">
                Qué pedir a quién
              </p>
              <ul className="mt-2 space-y-2">
                {handoff.questions_to_ask.map((question, index) => (
                  <li
                    key={`${question.department_id}-${index}`}
                    className="rounded-lg border border-white/10 bg-slate-950/40 p-3 text-sm"
                  >
                    <p className="text-xs font-semibold text-cyan-200">
                      {question.responsible || question.department_id}
                    </p>
                    <p className="mt-1 text-slate-200">{question.question}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {handoff.next_steps.length > 0 && (
            <div className="mt-4">
              <p className="text-xs uppercase tracking-wide text-cyan-200">
                Siguientes pasos por departamento
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-200">
                {handoff.next_steps.map((step) => (
                  <li key={step.department_id}>
                    <span className="font-semibold">{step.responsible}:</span>{" "}
                    {step.action}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <TraceTimeline trace={data.trace} />
    </div>
  );
}
