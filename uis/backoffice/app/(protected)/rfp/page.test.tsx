import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RfpPage from "@/app/(protected)/rfp/page";
import * as api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import type { RfpTicketListItem } from "@/lib/rfp-types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchRfpTickets: vi.fn(),
    uploadRfp: vi.fn(),
  };
});

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/hooks/useRfpRealtime", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/hooks/useRfpRealtime")>();
  return {
    ...actual,
    useRfpRealtime: () =>
      ({
        status: "open",
        attempt: 0,
        nextRetryMs: null,
        reconnected: false,
        liveTickets: new Map(),
        notifications: [],
        dismiss: vi.fn(),
        clear: vi.fn(),
      }) as ReturnType<typeof actual.useRfpRealtime>,
  };
});

const mockUseAuth = vi.mocked(useAuth);
const mockFetchTickets = vi.mocked(api.fetchRfpTickets);

const tickets: RfpTicketListItem[] = [
  {
    ticket_id: "t1",
    rfp_id: "RFP-2026-0001",
    status: "analisis_completo",
    pipeline_stage: "completado",
    original_filename: "modaviva.pdf",
    client_name: "ModaViva, S.L.",
    client_country: "Spain",
    currency: "EUR",
    discard_reason: null,
    error_message: null,
    created_at: "2026-08-03T10:00:00Z",
    updated_at: "2026-08-03T10:01:00Z",
  },
  {
    ticket_id: "t2",
    rfp_id: "RFP-2026-0002",
    status: "descartado",
    pipeline_stage: "descartado",
    original_filename: "rapidship.pdf",
    client_name: null,
    client_country: null,
    currency: null,
    discard_reason: "Pitch de transportista.",
    error_message: null,
    created_at: "2026-08-03T10:02:00Z",
    updated_at: "2026-08-03T10:03:00Z",
  },
];

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

describe("Recepción de RFPs — listado", () => {
  it("muestra los tickets y su estado real", async () => {
    mockFetchTickets.mockResolvedValue(tickets);

    render(<RfpPage />);

    await waitFor(() =>
      expect(screen.getByText("RFP-2026-0001")).toBeInTheDocument(),
    );
    expect(screen.getByText("ModaViva, S.L.")).toBeInTheDocument();
    expect(screen.getAllByText("Análisis completo").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Descartado").length).toBeGreaterThan(0);
    expect(screen.getByText("Pitch de transportista.")).toBeInTheDocument();
  });

  it("oculta la recepción a un usuario sin rol manager", async () => {
    mockUseAuth.mockReturnValue({
      token: "test-token",
      user: {
        id: "2",
        email: "user@trackflow.com",
        is_active: true,
        role: "user",
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

    render(<RfpPage />);

    expect(
      screen.getByText(/Solo un administrador o manager/),
    ).toBeInTheDocument();
    expect(mockFetchTickets).not.toHaveBeenCalled();
    await waitFor(() => expect(mockFetchTickets).not.toHaveBeenCalled());
  });
});
