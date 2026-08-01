export interface AnalysisResponse {
  total: number;
  valid: number;
  invalid: number;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  avg_satisfaction_cerrados: number | null;
  invalid_reasons: Record<string, number>;
}

export interface InvalidReasonMeta {
  key: string;
  label: string;
}

export const STATUS_LABELS: Record<string, string> = {
  abierto: "Abierto",
  cerrado: "Cerrado",
  descartado: "Descartado",
};

export const CATEGORY_LABELS: Record<string, string> = {
  seguimiento: "Seguimiento",
  devolución: "Devolución",
  consulta_general: "Consulta general",
  incidencia: "Incidencia",
};

export const INVALID_REASON_LABELS: Record<string, string> = {
  missing_customer_id: "Identificador de cliente faltante",
  missing_first_name: "Nombre faltante",
  missing_last_name: "Apellido faltante",
  missing_email: "Correo electrónico faltante",
  missing_phone: "Teléfono faltante",
  missing_department: "Departamento faltante",
  missing_status: "Estado faltante",
  missing_category: "Categoría faltante",
  invalid_email: "Correo electrónico inválido",
  invalid_department: "Departamento no permitido",
  invalid_status: "Estado no permitido",
  invalid_category: "Categoría no permitida",
  invalid_satisfaction_score: "Puntuación de satisfacción inválida",
};

export function describeReason(key: string): string {
  return INVALID_REASON_LABELS[key] ?? key.replace(/_/g, " ");
}
