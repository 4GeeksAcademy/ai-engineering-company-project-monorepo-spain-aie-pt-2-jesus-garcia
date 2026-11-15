export type RfpStatus =
  | "analizando"
  | "analisis_completo"
  | "descartado"
  | "error";

export const RFP_STATUS_LABELS: Record<RfpStatus, string> = {
  analizando: "Analizando",
  analisis_completo: "Análisis completo",
  descartado: "Descartado",
  error: "Error",
};

export const RFP_STATUS_STYLES: Record<RfpStatus, string> = {
  analizando: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
  analisis_completo: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  descartado: "bg-slate-500/15 text-slate-300 border-slate-500/30",
  error: "bg-rose-500/15 text-rose-300 border-rose-500/30",
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

export interface RfpDepartmentSection {
  department_id: string;
  responsible: string | null;
  key_aspects: RfpKeyAspect[];
  open_questions: string[];
  assumed_facts: Record<string, unknown>;
  unsupported_claims: Array<Record<string, unknown>>;
  approval_status: string | null;
  approver: string | null;
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
  discard_reason: string | null;
  error_message: string | null;
  handoff_status: string;
  updated_at: string;
}

export function isTerminalRfpStatus(status: RfpStatus): boolean {
  return status !== "analizando";
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
