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

export interface Supplier {
  id: string;
  name: string;
  country: string;
  categories: string[];
  rate_per_shipment: number;
  currency: string;
  updated_at: string;
  status: string;
  service_zone: string | null;
  contact_email: string | null;
  notes: string | null;
}

export interface SupplierCreate {
  name: string;
  country: string;
  categories: string[];
  rate_per_shipment: number;
  status?: string;
  service_zone?: string | null;
  contact_email?: string | null;
  notes?: string | null;
}

export interface SupplierUpdate {
  name?: string;
  categories?: string[];
  rate_per_shipment?: number;
  status?: string;
  service_zone?: string | null;
  contact_email?: string | null;
  notes?: string | null;
}

export const SUPPLIER_CATEGORIES: Record<string, string> = {
  carrier_last_mile: "Transporte última milla",
  carrier_international: "Transporte internacional",
  warehouse_supplies: "Suministros de almacén",
  packaging_materials: "Material de embalaje",
  reverse_logistics: "Logística inversa",
  fleet_maintenance: "Mantenimiento de flota",
  it_and_wms_software: "Software IT/WMS",
  cleaning_and_facilities: "Limpieza e instalaciones",
};

export const SUPPLIER_STATUSES: Record<string, string> = {
  active: "Activo",
  suspended: "Suspendido",
};

export const COUNTRY_FLAGS: Record<string, string> = {
  USA: "🇺🇸",
  Spain: "🇪🇸",
};

export interface Incident {
  id: string;
  title: string;
  description: string;
  origin: string;
  branch: string;
  category: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface IncidentCreate {
  title: string;
  description: string;
  origin: string;
  branch: string;
  category: string;
  status?: string;
}

export interface IncidentStatusUpdate {
  status: string;
}

export interface IncidentSummary {
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  by_origin: Record<string, number>;
  by_branch: Record<string, number>;
}

export const INCIDENT_STATUSES: Record<string, string> = {
  open: "Abierto",
  in_progress: "En curso",
  resolved: "Resuelto",
  discarded: "Descartado",
};

export const INCIDENT_CATEGORIES: Record<string, string> = {
  lost_parcel: "Paquete extraviado",
  delivery_failure: "Fallo de entrega",
  inventory_discrepancy: "Discrepancia de inventario",
  carrier_issue: "Problema con carrier",
  returns_issue: "Problema de devolución",
  warehouse_incident: "Incidente de almacén",
  system_failure: "Fallo de sistema",
  client_complaint: "Queja de cliente",
  other: "Otro",
};

export const INCIDENT_ORIGINS: Record<string, string> = {
  customer: "Cliente",
  branch: "Sucursal",
  internal: "Interno",
};

export const INCIDENT_BRANCHES: Record<string, string> = {
  central: "Central",
  la_warehouse: "Los Ángeles — Almacén",
  la_office: "Los Ángeles — Oficina",
  zaragoza_warehouse: "Zaragoza — Almacén",
  zaragoza_office: "Zaragoza — Oficina",
};

export const INCIDENT_STATUS_ORDER = ["open", "in_progress", "resolved", "discarded"];

export const INCIDENT_TRANSITIONS: Record<string, string[]> = {
  open: ["in_progress", "discarded"],
  in_progress: ["resolved", "discarded", "open"],
  resolved: ["in_progress"],
  discarded: [],
};

export function nextStatuses(status: string): string[] {
  return INCIDENT_TRANSITIONS[status] ?? [];
}
