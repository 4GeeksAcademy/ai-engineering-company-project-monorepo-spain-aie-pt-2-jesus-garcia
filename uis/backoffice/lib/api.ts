import type {
  AnalysisResponse,
  Incident,
  IncidentCreate,
  IncidentStatusUpdate,
  IncidentSummary,
  InventoryOrderCreate,
  InventoryOrderItem,
  SKU,
  SKUCreate,
  Supplier,
  SupplierCreate,
  SupplierUpdate,
} from "./types";

export class ApiRequestError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.detail = detail;
  }
}

function authHeaders(token?: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

type ResponseMode = "json" | "blob" | "none";

async function handleResponse<T>(res: Response, mode: ResponseMode): Promise<T> {
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const body = await res.json();
      detail = (body as { detail?: unknown }).detail ?? body;
    } catch (err) {
      console.error("Respuesta de error no es JSON válido", err);
      detail = res.statusText;
    }
    throw new ApiRequestError(
      res.status,
      typeof detail === "string" ? detail : res.statusText,
      detail,
    );
  }

  if (mode === "json") {
    try {
      return (await res.json()) as T;
    } catch {
      throw new ApiRequestError(
        res.status,
        "La respuesta del servidor no fue válida.",
      );
    }
  }

  if (mode === "blob") {
    return (await res.blob()) as T;
  }

  return undefined as T;
}

async function request<T>(
  path: string,
  options: RequestInit,
  mode: ResponseMode = "json",
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, options);
  } catch {
    throw new ApiRequestError(-1, "No se pudo conectar con el servidor");
  }
  return handleResponse<T>(res, mode);
}

export function friendlyError(err: unknown): string {
  if (err instanceof ApiRequestError) {
    switch (err.status) {
      case -1:
        return "No se pudo conectar con el servidor. Comprueba tu conexión e inténtalo de nuevo.";
      case 400:
        return "La solicitud no es válida. Revisa los datos enviados.";
      case 401:
        return "Sesión no autorizada. Vuelve a iniciar sesión.";
      case 403:
        return "No tienes permisos para realizar esta acción.";
      case 404:
        return "No se encontró el recurso solicitado.";
      case 409:
        return "El recurso ya existe o está en conflicto.";
      case 422:
        return "Los datos enviados no son válidos.";
      default:
        return "Ocurrió un error al procesar la solicitud. Inténtalo de nuevo.";
    }
  }
  return "No se pudo conectar con el servidor. Comprueba tu conexión e inténtalo de nuevo.";
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit & { token?: string } = {},
): Promise<T> {
  const { token, ...fetchOptions } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(fetchOptions.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  return request<T>(path, { ...fetchOptions, headers });
}

export async function analyzeCsv(
  file: File,
  token?: string | null,
): Promise<AnalysisResponse> {
  const formData = new FormData();
  formData.append("file", file);

  return request<AnalysisResponse>("/api/incidents/analyze", {
    method: "POST",
    headers: authHeaders(token),
    body: formData,
  });
}

export async function fetchExportCsv(token?: string | null): Promise<Blob> {
  return request<Blob>(
    "/api/incidents/results/export",
    { headers: authHeaders(token) },
    "blob",
  );
}

export async function fetchSuppliers(params?: {
  country?: string;
  category?: string;
  status?: string;
  search?: string;
}, token?: string | null): Promise<Supplier[]> {
  const searchParams = new URLSearchParams();
  if (params?.country) searchParams.set("country", params.country);
  if (params?.category) searchParams.set("category", params.category);
  if (params?.status) searchParams.set("status", params.status);
  if (params?.search) searchParams.set("search", params.search);

  const query = searchParams.toString();
  const url = `/api/suppliers${query ? `?${query}` : ""}`;

  return request<Supplier[]>(url, { headers: authHeaders(token) });
}

export async function fetchSupplier(
  id: string,
  token?: string | null,
): Promise<Supplier> {
  return request<Supplier>(`/api/suppliers/${id}`, {
    headers: authHeaders(token),
  });
}

export async function createSupplier(
  data: SupplierCreate,
  token?: string | null,
): Promise<Supplier> {
  return request<Supplier>("/api/suppliers", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(data),
  });
}

export async function updateSupplier(
  id: string,
  data: SupplierUpdate,
  token?: string | null,
): Promise<Supplier> {
  return request<Supplier>(`/api/suppliers/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(data),
  });
}

export async function deleteSupplier(id: string, token?: string | null): Promise<void> {
  return request<void>(
    `/api/suppliers/${id}`,
    { method: "DELETE", headers: authHeaders(token) },
    "none",
  );
}

export async function fetchIncidents(params?: {
  status?: string;
  origin?: string;
  branch?: string;
  category?: string;
}, token?: string | null): Promise<Incident[]> {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.set("status", params.status);
  if (params?.origin) searchParams.set("origin", params.origin);
  if (params?.branch) searchParams.set("branch", params.branch);
  if (params?.category) searchParams.set("category", params.category);

  const query = searchParams.toString();
  const url = `/api/incidents${query ? `?${query}` : ""}`;

  return request<Incident[]>(url, { headers: authHeaders(token) });
}

export async function fetchIncident(id: string, token?: string | null): Promise<Incident> {
  return request<Incident>(`/api/incidents/${id}`, {
    headers: authHeaders(token),
  });
}

export async function createIncident(
  data: IncidentCreate,
  token?: string | null,
): Promise<Incident> {
  return request<Incident>("/api/incidents", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(data),
  });
}

export async function updateIncidentStatus(
  id: string,
  data: IncidentStatusUpdate,
  token?: string | null,
): Promise<Incident> {
  return request<Incident>(`/api/incidents/${id}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(data),
  });
}

export async function fetchIncidentSummary(token?: string | null): Promise<IncidentSummary> {
  return request<IncidentSummary>("/api/incidents/summary", {
    headers: authHeaders(token),
  });
}

export async function fetchInventoryProducts(token?: string | null): Promise<SKU[]> {
  return request<SKU[]>("/api/inventory/products", {
    headers: authHeaders(token),
  });
}

export async function fetchInventoryProduct(
  id: number,
  token?: string | null,
): Promise<SKU> {
  return request<SKU>(`/api/inventory/products/${id}`, {
    headers: authHeaders(token),
  });
}

export async function createInventoryProduct(
  data: SKUCreate,
  token?: string | null,
): Promise<SKU> {
  return request<SKU>("/api/inventory/products", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(data),
  });
}

export async function fetchInventoryOrders(token?: string | null): Promise<InventoryOrderItem[]> {
  return request<InventoryOrderItem[]>("/api/inventory/orders", {
    headers: authHeaders(token),
  });
}

export async function createInboundOrder(
  data: Omit<InventoryOrderCreate, "order_type">,
  token?: string | null,
): Promise<InventoryOrderItem> {
  return request<InventoryOrderItem>("/api/inventory/orders/inbound", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(data),
  });
}

export async function createOutboundOrder(
  data: Omit<InventoryOrderCreate, "order_type">,
  token?: string | null,
): Promise<InventoryOrderItem> {
  return request<InventoryOrderItem>("/api/inventory/orders/outbound", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(data),
  });
}
