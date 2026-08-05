import type { AnalysisResponse, Supplier, SupplierCreate, SupplierUpdate } from "./types";

export class ApiRequestError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

export async function analyzeCsv(file: File): Promise<AnalysisResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/api/incidents/analyze", {
    method: "POST",
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

export async function fetchExportCsv(): Promise<Blob> {
  const response = await fetch("/api/incidents/results/export");

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
}): Promise<Supplier[]> {
  const searchParams = new URLSearchParams();
  if (params?.country) searchParams.set("country", params.country);
  if (params?.category) searchParams.set("category", params.category);
  if (params?.status) searchParams.set("status", params.status);

  const query = searchParams.toString();
  const url = `/api/suppliers${query ? `?${query}` : ""}`;

  const response = await fetch(url);

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

export async function fetchSupplier(id: string): Promise<Supplier> {
  const response = await fetch(`/api/suppliers/${id}`);

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

export async function createSupplier(data: SupplierCreate): Promise<Supplier> {
  const response = await fetch("/api/suppliers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  data: SupplierUpdate
): Promise<Supplier> {
  const response = await fetch(`/api/suppliers/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
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

export async function deleteSupplier(id: string): Promise<void> {
  const response = await fetch(`/api/suppliers/${id}`, {
    method: "DELETE",
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
