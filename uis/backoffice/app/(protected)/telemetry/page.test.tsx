import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TelemetryPage from "@/app/(protected)/telemetry/page";
import * as api from "@/lib/api";
import type { TelemetryReport } from "@/lib/types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchTelemetryReport: vi.fn(),
  };
});

const mockFetchReport = vi.mocked(api.fetchTelemetryReport);

const report: TelemetryReport = {
  period: {
    from: "2026-06-14T00:00:00Z",
    to: "2026-06-16T00:00:00Z",
  },
  metrics: {
    events_per_day: [
      { date: "2026-06-14", event_type: "login_failed", event_count: 2 },
      { date: "2026-06-15", event_type: "page_view", event_count: 10 },
    ],
    error_rate_by_day: [
      {
        date: "2026-06-14",
        event_count: 12,
        error_count: 3,
        error_rate: 0.25,
      },
    ],
    errors_by_type: [
      { date: "2026-06-14", event_type: "login_failed", error_count: 2 },
      {
        date: "2026-06-15",
        event_type: "frontend_error_uncaught",
        error_count: 1,
      },
    ],
    latency_per_day: [
      {
        date: "2026-06-14",
        avg_ms: 30,
        p50_ms: 30,
        p95_ms: 40.8,
        sample_count: 2,
      },
    ],
    auth_failure_rate: [
      { date: "2026-06-14", failed: 2, succeeded: 1, failure_rate: 0.6667 },
    ],
  },
};

const emptyReport: TelemetryReport = {
  period: report.period,
  metrics: {
    events_per_day: [],
    error_rate_by_day: [],
    errors_by_type: [],
    latency_per_day: [],
    auth_failure_rate: [],
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  mockFetchReport.mockResolvedValue(report);
});

describe("TelemetryPage", () => {
  it("muestra el periodo, los resúmenes y las cinco métricas", async () => {
    render(<TelemetryPage />);

    expect(await screen.findByText("Telemetría")).toBeInTheDocument();
    expect(
      await screen.findByText("2026-06-14T00:00:00Z"),
    ).toBeInTheDocument();
    expect(screen.getByText("2026-06-16T00:00:00Z")).toBeInTheDocument();

    expect(screen.getByText("Eventos totales").nextElementSibling).toHaveTextContent(
      "12",
    );
    expect(screen.getByText("Tasa de error").nextElementSibling).toHaveTextContent(
      "25.0%",
    );
    expect(
      screen.getByText("Latencia media").nextElementSibling,
    ).toHaveTextContent("30.0 ms");
    expect(
      screen.getByText("Fallos de login").nextElementSibling,
    ).toHaveTextContent("66.7%");

    const events = await screen.findByRole("region", { name: "Eventos por día" });
    expect(within(events).getByText("login_failed")).toBeInTheDocument();
    expect(within(events).getByText("page_view")).toBeInTheDocument();

    expect(
      screen.getByRole("region", { name: "Tasa de error por día" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Errores por tipo" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Latencia por día" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Fallos de autenticación" }),
    ).toBeInTheDocument();
  });

  it("vuelve a pedir el informe al cambiar el rango de fechas", async () => {
    render(<TelemetryPage />);

    await screen.findByRole("region", { name: "Eventos por día" });
    await act(async () => {
      fireEvent.change(screen.getByLabelText("Hasta"), {
        target: { value: "2026-06-20" },
      });
    });

    await vi.waitFor(() => {
      expect(mockFetchReport).toHaveBeenLastCalledWith({
        start_date: expect.stringMatching(/T00:00:00Z$/),
        end_date: "2026-06-21T00:00:00.000Z",
      });
    });
  });

  it("muestra un estado vacío cuando no hay eventos en el periodo", async () => {
    mockFetchReport.mockResolvedValue(emptyReport);
    render(<TelemetryPage />);

    expect(
      await screen.findByText("No hay eventos en el periodo seleccionado."),
    ).toBeInTheDocument();
    expect(screen.getByText("Eventos totales")).toBeInTheDocument();
    expect(screen.getAllByText("—")).toHaveLength(3);
  });

  it("muestra el error y permite reintentar", async () => {
    mockFetchReport.mockRejectedValueOnce(new Error("boom"));
    render(<TelemetryPage />);

    expect(await screen.findByText(/Error:/)).toBeInTheDocument();

    mockFetchReport.mockResolvedValue(report);
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(
      await screen.findByRole("region", { name: "Eventos por día" }),
    ).toBeInTheDocument();
  });
});
