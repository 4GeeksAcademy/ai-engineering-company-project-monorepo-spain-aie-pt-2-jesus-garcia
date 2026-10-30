import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ReportingPage from "@/app/(protected)/reporting/page";
import * as api from "@/lib/api";
import { ApiRequestError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import type { PipelineRunLatest, WeeklyPerformanceReport } from "@/lib/types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchWeeklyPerformance: vi.fn(),
    fetchLatestPipelineRun: vi.fn(),
    triggerPipelineRun: vi.fn(),
  };
});

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

const mockUseAuth = vi.mocked(useAuth);
const mockFetchWeekly = vi.mocked(api.fetchWeeklyPerformance);
const mockFetchLatest = vi.mocked(api.fetchLatestPipelineRun);
const mockTrigger = vi.mocked(api.triggerPipelineRun);

const report: WeeklyPerformanceReport = {
  week_start: "2026-07-13",
  frozen: true,
  stale: false,
  computed_at: "2026-07-20T08:00:00Z",
  entries: [
    {
      warehouse: "los_angeles",
      client_id: "fashion-co",
      inbound_units_count: 150,
      outbound_orders_count: 3,
      stockout_events_count: 1,
      discrepancy_events_count: 1,
      discrepancy_rate: 0.333333,
    },
    {
      warehouse: "zaragoza",
      client_id: "home-deco",
      inbound_units_count: 70,
      outbound_orders_count: 2,
      stockout_events_count: 0,
      discrepancy_events_count: 0,
      discrepancy_rate: 0,
    },
  ],
};

const run: PipelineRunLatest = {
  run_id: "run-1",
  status: "success",
  week_start: "2026-07-13",
  started_at: "2026-07-20T08:00:00Z",
  finished_at: "2026-07-20T08:00:42Z",
  rows_extracted: 10,
  rows_valid: 10,
  rows_rejected: 0,
  rows_written: 2,
  quality_status: "passed",
  error_message: null,
  source_fingerprint: "abc",
  instrumentation_since: "2026-07-01",
  stale: false,
};

function mockAuth() {
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
}

beforeEach(() => {
  vi.clearAllMocks();
  mockAuth();
  mockFetchWeekly.mockResolvedValue(report);
  mockFetchLatest.mockResolvedValue(run);
  mockTrigger.mockResolvedValue({
    run_id: "flow-run-1",
    flow_run_id: "flow-run-1",
    status: "scheduled",
  });
});

describe("ReportingPage", () => {
  it("muestra el resumen semanal y el detalle por almacén/cliente", async () => {
    render(<ReportingPage />);

    expect(await screen.findByText("Desempeño semanal")).toBeInTheDocument();
    expect((await screen.findAllByText(/2026-07-13/)).length).toBeGreaterThan(0);
    expect(screen.getByText("congelada")).toBeInTheDocument();

    expect(screen.getByText("Volumen de entrada").nextElementSibling).toHaveTextContent(
      "220",
    );
    expect(
      screen.getByText("Throughput de salida").nextElementSibling,
    ).toHaveTextContent("5");
    expect(
      screen.getByText("Tasa de discrepancia").nextElementSibling,
    ).toHaveTextContent("20.00%");

    const table = await screen.findByRole("region", {
      name: "Detalle por almacén y cliente",
    });
    expect(within(table).getByText("Los Ángeles")).toBeInTheDocument();
    expect(within(table).getByText("fashion-co")).toBeInTheDocument();
    expect(within(table).getByText("Zaragoza")).toBeInTheDocument();
    expect(within(table).getByText("home-deco")).toBeInTheDocument();
  });

  it("muestra el estado de la última corrida", async () => {
    render(<ReportingPage />);

    const status = await screen.findByRole("region", {
      name: "Estado del pipeline",
    });
    expect(within(status).getByText("success")).toBeInTheDocument();
    expect(within(status).getByText(/Calidad: passed/)).toBeInTheDocument();
    expect(within(status).getByText("10")).toBeInTheDocument();
  });

  it("muestra el estado vacío si no hay semanas calculadas", async () => {
    mockFetchWeekly.mockRejectedValue(
      new ApiRequestError(404, "No hay semanas calculadas."),
    );

    render(<ReportingPage />);

    expect(
      await screen.findByText(/Aún no hay semanas calculadas/),
    ).toBeInTheDocument();
  });

  it("dispara una corrida manual tras confirmar", async () => {
    const user = userEvent.setup();
    render(<ReportingPage />);

    await screen.findByText("Desempeño semanal");
    await user.click(screen.getByRole("button", { name: "Ejecutar ahora" }));
    expect(screen.getByText("Ejecutar pipeline")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ejecutar" }));

    await waitFor(() =>
      expect(mockTrigger).toHaveBeenCalledWith(
        { week_start: undefined },
        "test-token",
      ),
    );
  });

  it("filtra por una semana concreta", async () => {
    render(<ReportingPage />);

    await screen.findByText("Desempeño semanal");
    fireEvent.change(screen.getByLabelText("Semana del reporte"), {
      target: { value: "2026-07-06" },
    });

    await waitFor(() =>
      expect(mockFetchWeekly).toHaveBeenCalledWith(
        { week_start: "2026-07-06" },
        "test-token",
      ),
    );
  });
});
