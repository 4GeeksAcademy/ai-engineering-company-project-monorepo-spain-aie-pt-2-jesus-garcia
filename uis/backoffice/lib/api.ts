import type { AnalysisResponse, Supplier, SupplierCreate, SupplierUpdate } from "./types";

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

  const res = await fetch(path, { ...fetchOptions, headers });

  if (!res.ok) {
    let detail: unknown;
    try {
      const body = await res.json();
      detail = body.detail ?? body;
    } catch {
      detail = res.statusText;
    }
    throw new ApiRequestError(
      res.status,
      typeof detail === "string" ? detail : res.statusText,
      detail,
    );
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function analyzeCsv(
  file: File,
  token?: string | null,
): Promise<AnalysisResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/api/incidents/analyze", {
    method: "POST",
    headers: { ...authHeaders(token) },
    body: formData,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {}
    throw new ApiRequestError(response.status, detail);
  }

  return response.json() as Promise<AnalysisResponse>;
}

export async function fetchExportCsv(token?: string | null): Promise<Blob> {
  const response = await fetch("/api/incidents/results/export", {
    headers: { ...authHeaders(token) },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {}
    throw new ApiRequestError(response.status, detail);
  }

  return response.blob();
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

  const response = await fetch(url, { headers: { ...authHeaders(token) } });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {}
    throw new ApiRequestError(response.status, detail);
  }

  return response.json() as Promise<Supplier[]>;
}

export async function fetchSupplier(
  id: string,
  token?: string | null,
): Promise<Supplier> {
  const response = await fetch(`/api/suppliers/${id}`, {
    headers: { ...authHeaders(token) },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {}
    throw new ApiRequestError(response.status, detail);
  }

  return response.json() as Promise<Supplier>;
}

export async function createSupplier(
  data: SupplierCreate,
  token?: string | null,
): Promise<Supplier> {
  const response = await fetch("/api/suppliers", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {}
    throw new ApiRequestError(response.status, detail);
  }

  return response.json() as Promise<Supplier>;
}

export async function updateSupplier(
  id: string,
  data: SupplierUpdate,
  token?: string | null,
): Promise<Supplier> {
  const response = await fetch(`/api/suppliers/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {}
    throw new ApiRequestError(response.status, detail);
  }

  return response.json() as Promise<Supplier>;
}

export async function deleteSupplier(id: string, token?: string | null): Promise<void> {
  const response = await fetch(`/api/suppliers/${id}`, {
    method: "DELETE",
    headers: { ...authHeaders(token) },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {}
    throw new ApiRequestError(response.status, detail);
  }
}
