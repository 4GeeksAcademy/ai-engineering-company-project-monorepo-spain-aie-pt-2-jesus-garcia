import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BackofficePage from "@/app/(protected)/page";
import * as api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import type { AnalysisResponse } from "@/lib/types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    analyzeCsv: vi.fn(),
    fetchTaskStatus: vi.fn(),
  };
});

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/components/IncidentUploader", () => ({
  IncidentUploader: ({
    onFile,
  }: {
    onFile: (file: File) => void;
    loading: boolean;
  }) => (
    <button
      onClick={() =>
        onFile(new File(["a,b\n1,2"], "COMPANY.csv", { type: "text/csv" }))
      }
    >
      Subir CSV
    </button>
  ),
}));

const mockUseAuth = vi.mocked(useAuth);
const mockAnalyze = vi.mocked(api.analyzeCsv);
const mockStatus = vi.mocked(api.fetchTaskStatus);

const analysis: AnalysisResponse = {
  total: 5,
  valid: 5,
  invalid: 0,
  by_status: { abierto: 2, cerrado: 2, descartado: 1 },
  by_category: { incidencia: 2, seguimiento: 1 },
  avg_satisfaction_cerrados: 8.5,
  invalid_reasons: {},
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUseAuth.mockReturnValue({
    token: "test-token",
    user: {
      id: "1",
      email: "ops@trackflow.com",
      is_active: true,
      role: "manager",
      created_at: "",
    },
    isLoading: false,
    isAuthenticated: true,
    sessionError: null,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    retryValidation: vi.fn(),
  } as ReturnType<typeof useAuth>);
});

describe("Análisis de incidentes (asíncrono)", () => {
  it("encola la tarea y muestra el resultado cuando termina", async () => {
    mockAnalyze.mockResolvedValue({ task_id: "task-123" });
    mockStatus.mockResolvedValue({
      task_id: "task-123",
      status: "success",
      result: analysis,
    });

    render(<BackofficePage />);
    fireEvent.click(screen.getByRole("button", { name: "Subir CSV" }));

    await waitFor(() =>
      expect(screen.getByText("Total procesados")).toBeInTheDocument(),
    );

    expect(mockAnalyze).toHaveBeenCalledTimes(1);
    expect(mockStatus).toHaveBeenCalledWith("task-123", "test-token");
    expect(screen.getByText("Registros válidos")).toBeInTheDocument();
    expect(screen.getByText("Descargar último CSV")).toBeInTheDocument();
  });

  it("muestra el error y el task_id cuando la tarea falla", async () => {
    mockAnalyze.mockResolvedValue({ task_id: "task-err" });
    mockStatus.mockResolvedValue({
      task_id: "task-err",
      status: "failure",
      result: "RuntimeError: boom",
    });

    render(<BackofficePage />);
    fireEvent.click(screen.getByRole("button", { name: "Subir CSV" }));

    await waitFor(() =>
      expect(screen.getByText(/RuntimeError: boom/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/task_id: task-err/)).toBeInTheDocument();
    expect(screen.queryByText("Total procesados")).not.toBeInTheDocument();
  });

  it("muestra el error de encolado sin consultar el estado", async () => {
    mockAnalyze.mockRejectedValue(new api.ApiRequestError(400, "CSV inválido"));

    render(<BackofficePage />);
    fireEvent.click(screen.getByRole("button", { name: "Subir CSV" }));

    await waitFor(() =>
      expect(screen.getByText(/La solicitud no es válida/)).toBeInTheDocument(),
    );
    expect(mockStatus).not.toHaveBeenCalled();
  });
});
