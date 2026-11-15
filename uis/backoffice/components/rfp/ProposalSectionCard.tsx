"use client";

import type { ReactNode } from "react";
import {
  DEPARTMENT_LABELS,
  SECTION_STATUS_LABELS,
  SECTION_STATUS_STYLES,
  type RfpDepartmentSection,
  type RfpEvaluationCriterion,
} from "@/lib/rfp-types";

function Criterion({
  label,
  criterion,
  children,
}: {
  label: string;
  criterion: RfpEvaluationCriterion;
  children?: ReactNode;
}) {
  return (
    <div
      className={`rounded-lg border p-3 ${
        criterion.pass
          ? "border-emerald-500/25 bg-emerald-500/5"
          : "border-rose-500/25 bg-rose-500/5"
      }`}
    >
      <p className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide">
        <span className="text-slate-300">{label}</span>
        <span className={criterion.pass ? "text-emerald-300" : "text-rose-300"}>
          {criterion.pass ? "OK" : "Falla"}
        </span>
      </p>
      {children}
    </div>
  );
}

export function ProposalSectionCard({
  section,
}: {
  section: RfpDepartmentSection;
}) {
  const evaluation = section.evaluation_results;
  if (!section.draft_content && !evaluation) return null;

  const status = section.generation_status ?? "pendiente";
  const provisional = section.needs_human_review;

  return (
    <article className="rounded-xl border border-white/10 bg-slate-900/60 p-5">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-white">
            {DEPARTMENT_LABELS[section.department_id] ?? section.department_id}
          </h3>
          <p className="text-xs text-slate-400">
            Responsable: {section.responsible ?? "—"} ·{" "}
            {section.iteration_count} iteración(es)
          </p>
        </div>
        <span
          className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${
            SECTION_STATUS_STYLES[status] ?? SECTION_STATUS_STYLES.pendiente
          }`}
        >
          {SECTION_STATUS_LABELS[status] ?? status}
        </span>
      </header>

      {provisional && (
        <div className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-100">
          <p className="font-semibold">
            Borrador provisional: requiere revisión humana antes de enviarlo al
            cliente.
          </p>
          {section.review_reason && (
            <p className="mt-1 whitespace-pre-line text-xs text-amber-200/90">
              {section.review_reason}
            </p>
          )}
        </div>
      )}

      {evaluation && (
        <>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <Criterion label="Legibilidad" criterion={evaluation.readability}>
              {typeof evaluation.readability.score === "number" && (
                <p className="mt-2 text-sm text-slate-200">
                  Score {evaluation.readability.score}
                </p>
              )}
            </Criterion>
            <Criterion label="Pertinencia" criterion={evaluation.relevance}>
              {Boolean(evaluation.relevance.missing_aspects?.length) && (
                <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-rose-200">
                  {evaluation.relevance.missing_aspects?.map((aspect) => (
                    <li key={aspect}>{aspect}</li>
                  ))}
                </ul>
              )}
            </Criterion>
            <Criterion label="Cumplimiento" criterion={evaluation.compliance}>
              {Boolean(evaluation.compliance.violations?.length) && (
                <ul className="mt-2 space-y-2 text-xs text-rose-200">
                  {evaluation.compliance.violations?.map((violation, index) => (
                    <li key={`${violation.rule_id}-${index}`}>
                      <span className="font-semibold">{violation.rule_id}</span>
                      {": "}
                      {violation.message}
                      {violation.required_change && (
                        <span className="block text-rose-300/80">
                          Cambio requerido: {violation.required_change}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Criterion>
          </div>

          {evaluation.feedback_for_generator && (
            <details className="mt-3 rounded-lg border border-white/10 bg-slate-950/40 p-3">
              <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-slate-300">
                Feedback al generador
              </summary>
              <p className="mt-2 whitespace-pre-line text-xs text-slate-300">
                {evaluation.feedback_for_generator}
              </p>
            </details>
          )}
        </>
      )}

      {section.draft_content && (
        <details className="mt-3 rounded-lg border border-white/10 bg-slate-950/40 p-3">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-cyan-200">
            Ver borrador de la sección
          </summary>
          <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap text-xs text-slate-200">
            {section.draft_content}
          </pre>
        </details>
      )}
    </article>
  );
}
