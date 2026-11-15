export type RfpStatus =
  | "analizando"
  | "analisis_completo"
  | "generando_borrador"
  | "en_evaluación"
  | "needs_human_review"
  | "esperando_aprobación"
  | "terminado"
  | "descartado"
  | "error";

export const RFP_STATUS_LABELS: Record<RfpStatus, string> = {
  analizando: "Analizando",
  analisis_completo: "Análisis completo",
  generando_borrador: "Generando borrador",
  "en_evaluación": "En evaluación",
  needs_human_review: "Revisión humana",
  "esperando_aprobación": "Esperando aprobación",
  terminado: "Terminado",
  descartado: "Descartado",
  error: "Error",
};

export const RFP_STATUS_STYLES: Record<RfpStatus, string> = {
  analizando: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
  analisis_completo: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  generando_borrador: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
  "en_evaluación": "bg-violet-500/15 text-violet-300 border-violet-500/30",
  needs_human_review: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  "esperando_aprobación": "bg-teal-500/15 text-teal-300 border-teal-500/30",
  terminado: "bg-emerald-500/15 text-emerald-200 border-emerald-500/40",
  descartado: "bg-slate-500/15 text-slate-300 border-slate-500/30",
  error: "bg-rose-500/15 text-rose-300 border-rose-500/30",
};

export const RFP_PROPOSAL_ACTIVE_STATUSES: RfpStatus[] = [
  "generando_borrador",
  "en_evaluación",
];

export const RFP_POLLING_STATUSES: RfpStatus[] = [
  "analizando",
  "generando_borrador",
  "en_evaluación",
];

export const SECTION_STATUS_LABELS: Record<string, string> = {
  generando: "Generando",
  "en_evaluación": "En evaluación",
  evaluated_pass: "Evaluada",
  needs_human_review: "Revisión humana",
  pendiente: "Pendiente",
};

export const SECTION_STATUS_STYLES: Record<string, string> = {
  generando: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
  "en_evaluación": "bg-violet-500/15 text-violet-300 border-violet-500/30",
  evaluated_pass: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  needs_human_review: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  pendiente: "bg-slate-500/15 text-slate-300 border-slate-500/30",
};

export const DEPARTMENT_LABELS: Record<string, string> = {
  warehouse: "Warehouse Operations",
  lastmile: "Last Mile and Carrier Management",
  reverse: "Reverse Logistics",
};

export const DEPARTMENT_SHORT_LABELS: Record<string, string> = {
  warehouse: "Almacenamiento",
  lastmile: "Última milla",
  reverse: "Logística inversa",
};

export const SERVICE_LABELS: Record<string, string> = {
  warehousing: "Almacenamiento",
  last_mile: "Última milla",
  reverse_logistics: "Logística inversa",
};

export interface RfpUploadResponse {
  ticket_id: string;
  rfp_id: string;
  status: RfpStatus;
  task_id: string | null;
}

export interface RfpTicketListItem {
  ticket_id: string;
  rfp_id: string;
  status: RfpStatus;
  pipeline_stage: string | null;
  original_filename: string;
  client_name: string | null;
  client_country: string | null;
  currency: string | null;
  discard_reason: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface RfpKeyAspect {
  aspect: string;
  detail: string;
  evidence?: string;
  confidence?: "high" | "medium" | "low" | string;
}

export interface RfpEvaluationViolation {
  rule_id: string;
  message: string;
  excerpt?: string;
  required_change?: string;
}

export interface RfpEvaluationCriterion {
  pass: boolean;
  score?: number;
  details?: Record<string, unknown>;
  missing_aspects?: string[];
  rule_ids?: string[];
  violations?: RfpEvaluationViolation[];
}

export interface RfpEvaluationResult {
  section_id?: string;
  department_id?: string;
  iteration?: number;
  readability: RfpEvaluationCriterion;
  relevance: RfpEvaluationCriterion;
  compliance: RfpEvaluationCriterion;
  overall_pass: boolean;
  feedback_for_generator?: string;
}

export interface RfpDepartmentSection {
  department_id: string;
  responsible: string | null;
  key_aspects: RfpKeyAspect[];
  open_questions: string[];
  assumed_facts: Record<string, unknown>;
  unsupported_claims: Array<Record<string, unknown>>;
  approval_status: string | null;
  approver: string | null;
  draft_content: string | null;
  draft_payload: Record<string, unknown> | null;
  evaluation_results: RfpEvaluationResult | null;
  generation_status: string | null;
  iteration_count: number;
  needs_human_review: boolean;
  review_reason: string | null;
}

export interface RfpMetadata {
  client_name: string | null;
  client_country: string | null;
  currency: string | null;
  language: string | null;
  services_requested: string[];
  departments_needed: string[];
  monthly_volume: number | null;
  deadline: string | null;
  budget_range: string | null;
  contact: Record<string, string>;
  scope_notes: string[];
  unknown_services: string[];
  missing_fields: string[];
  readability_metrics: Record<string, number | string>;
  document_metadata: Record<string, unknown>;
}

export interface RfpTicketDetail {
  ticket_id: string;
  rfp_id: string;
  status: RfpStatus;
  pipeline_stage: string | null;
  original_filename: string;
  raw_pdf_path: string;
  markdown_path: string | null;
  file_sha256: string;
  classification: Record<string, unknown> | null;
  discard_reason: string | null;
  error_message: string | null;
  handoff_status: string;
  handoff: RfpHandoff | null;
  proposal_status: string | null;
  proposal_error: string | null;
  approval_status: string | null;
  approval_thread_id: string | null;
  approval_error: string | null;
  final_document_ready: boolean;
  metadata: RfpMetadata | null;
  sections: RfpDepartmentSection[];
  created_at: string;
  updated_at: string;
}

export interface RfpQuestion {
  department_id: string;
  responsible: string;
  question: string;
}

export interface RfpHandoffDepartment {
  department_id: string;
  department_label: string;
  responsible: string | null;
  focus: string | null;
  key_aspects: RfpKeyAspect[];
  open_questions: string[];
}

export interface RfpHandoff {
  contract_version: string;
  ticket_id: string;
  rfp_id: string;
  status: string;
  generated_at: string;
  client: {
    name: string | null;
    country: string | null;
    currency: string | null;
    contact: Record<string, string>;
  };
  currency: string | null;
  services_requested: string[];
  unknown_services: string[];
  departments: RfpHandoffDepartment[];
  questions_to_ask: RfpQuestion[];
  conflicts: Array<Record<string, unknown>>;
  sales_summary: string;
  next_steps: Array<{
    department_id: string;
    responsible: string;
    action: string;
  }>;
  source: Record<string, unknown>;
}

export interface RfpTicketStatus {
  ticket_id: string;
  rfp_id: string;
  status: RfpStatus;
  pipeline_stage: string | null;
  proposal_status: string | null;
  approval_status: string | null;
  discard_reason: string | null;
  error_message: string | null;
  handoff_status: string;
  updated_at: string;
}

export interface RfpProposalStartResponse {
  ticket_id: string;
  task_id: string | null;
  status: RfpStatus;
}

export interface RfpProposalSection {
  section_id: string;
  department_id: string;
  department_label: string | null;
  responsible: string | null;
  status: string;
  provisional: boolean;
  iteration_count: number;
  draft_content: string | null;
  draft_payload: Record<string, unknown> | null;
  evaluation_results: RfpEvaluationResult | null;
  review_reason: string | null;
  approval_status: string | null;
  approver: string | null;
}

export interface RfpProposal {
  ticket_id: string;
  rfp_id: string | null;
  status: RfpStatus;
  generated_at: string | null;
  client: Record<string, unknown>;
  client_country: string | null;
  currency: string | null;
  services_requested: string[];
  sections: RfpProposalSection[];
  needs_human_review_sections: string[];
  metrics: Record<string, number>;
  source_handoff: Record<string, unknown>;
}

export function isTerminalRfpStatus(status: RfpStatus): boolean {
  return ![
    "analizando",
    "generando_borrador",
    "en_evaluación",
    "esperando_aprobación",
  ].includes(status);
}

export const RFP_APPROVAL_STATUS_LABELS: Record<string, string> = {
  pending_approval: "Pendiente de aprobación",
  approved: "Aprobada",
  rejected: "Rechazada",
  changes_requested: "Cambios solicitados",
  encolado: "Encolado",
  resuming: "Reanudando",
  completed: "Completada",
  rejected_run: "Rechazada",
  error: "Error",
};

export const RFP_APPROVAL_STATUS_STYLES: Record<string, string> = {
  pending_approval: "bg-teal-500/15 text-teal-300 border-teal-500/30",
  approved: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  rejected: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  changes_requested: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  encolado: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
  resuming: "bg-violet-500/15 text-violet-300 border-violet-500/30",
  completed: "bg-emerald-500/15 text-emerald-200 border-emerald-500/40",
  rejected_run: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  error: "bg-rose-500/15 text-rose-300 border-rose-500/30",
};

export interface RfpApprovalPacket {
  department_id: string;
  department_label: string | null;
  responsible: string | null;
  approval_status: string | null;
  approval_round: number;
  interrupt_id: string | null;
  provisional: boolean;
  packet: {
    section_markdown?: string;
    title?: string | null;
    executive_summary?: string | null;
    pricing?: Array<Record<string, unknown>>;
    sla?: Record<string, unknown>;
    discount_tiers?: Array<Record<string, unknown>>;
    turnaround?: Record<string, unknown>;
    capacity?: Record<string, unknown>;
    carriers?: Array<Record<string, unknown>>;
    assumptions?: string[];
    open_questions?: string[];
    evaluation?: RfpEvaluationResult | Record<string, unknown>;
    client?: Record<string, unknown>;
    client_country?: string | null;
    currency?: string | null;
    deadline?: string | null;
    approval_round?: number;
    max_rounds?: number;
    allowed_actions?: string[];
    conflicts?: Array<Record<string, unknown>>;
    decision_requirements?: Record<string, unknown>;
    [key: string]: unknown;
  };
}

export interface RfpApprovalDecisionSummary {
  department_id: string;
  department_label: string | null;
  responsible: string | null;
  approval_status: string | null;
  approver: string | null;
  approved_at: string | null;
  comment: string | null;
  provisional: boolean;
  approval_round: number;
}

export interface RfpApprovals {
  ticket_id: string;
  rfp_id: string | null;
  status: RfpStatus;
  approval_status: string | null;
  thread_id: string | null;
  run: number;
  max_rounds: number;
  pending: RfpApprovalPacket[];
  decisions: RfpApprovalDecisionSummary[];
  final_document_ready: boolean;
}

export type RfpApprovalAction = "approve" | "reject" | "request_changes";

export interface RfpApprovalDecision {
  action: RfpApprovalAction;
  approver: string;
  comment?: string | null;
  interrupt_id: string;
  acknowledge_provisional?: boolean;
}

export interface RfpApprovalResumeResponse {
  ticket_id: string;
  task_id: string | null;
  department_id: string;
  action: string;
  status: string;
  pending_remaining: number;
}

export interface RfpApprovalStartResponse {
  ticket_id: string;
  task_id: string | null;
  status: string;
}

export interface RfpFinalDocument {
  contract_version: string;
  ticket_id: string;
  currency: string | null;
  sections: Array<Record<string, unknown>>;
  approved_by: Array<{
    department_id: string;
    department_label: string;
    responsible: string;
    approver: string;
    approved_at: string;
    comment: string | null;
    provisional: boolean;
  }>;
  markdown: string;
  document_path: string | null;
  generated_at: string | null;
}

export interface RfpTraceEvent {
  event_id: string;
  part: number;
  sequence: number;
  node: string;
  agent: string | null;
  department_id: string | null;
  thread_id: string | null;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  timestamp: string | null;
  duration_ms: number | null;
}

export interface RfpArbitration {
  round: number;
  trigger_id: string;
  arbitrator: string | null;
  rule: string | null;
  affected_sections: string[];
  resolution: Record<string, unknown>;
  resolved: boolean;
  created_at: string | null;
}

export interface RfpTrace {
  ticket_id: string;
  events: RfpTraceEvent[];
  arbitrations: RfpArbitration[];
}

export function formatRfpDate(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("es-ES", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(parsed);
}
