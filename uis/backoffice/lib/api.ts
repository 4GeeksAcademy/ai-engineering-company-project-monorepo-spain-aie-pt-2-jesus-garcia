import type { AnalysisResponse } from "./types";

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
