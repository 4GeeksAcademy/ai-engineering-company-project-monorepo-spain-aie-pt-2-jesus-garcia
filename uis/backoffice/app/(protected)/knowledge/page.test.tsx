import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import KnowledgePage from "@/app/(protected)/knowledge/page";
import { ApiRequestError } from "@/lib/api";
import { askKnowledge } from "@/lib/knowledge-api";
import { useAuth } from "@/contexts/AuthContext";

vi.mock("@/lib/knowledge-api", () => ({
  askKnowledge: vi.fn(),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

const mockUseAuth = vi.mocked(useAuth);
const mockAskKnowledge = vi.mocked(askKnowledge);

function mockAuth() {
  mockUseAuth.mockReturnValue({
    token: "test-token",
    user: {
      id: "1",
      email: "sales@trackflow.com",
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
});

describe("KnowledgePage", () => {
  it("muestra la respuesta generada por el endpoint", async () => {
    mockAskKnowledge.mockResolvedValue({
      answer: "La ventana de devolución estándar es de 30 días.",
    });

    render(<KnowledgePage />);
    await userEvent.type(
      screen.getByLabelText("Pregunta"),
      "¿Cuál es la ventana de devolución?",
    );
    await userEvent.click(screen.getByRole("button", { name: "Consultar" }));

    expect(
      await screen.findByText("La ventana de devolución estándar es de 30 días."),
    ).toBeInTheDocument();
    expect(mockAskKnowledge).toHaveBeenCalledWith(
      "¿Cuál es la ventana de devolución?",
      "test-token",
    );
  });

  it("muestra un error cuando la API falla", async () => {
    mockAskKnowledge.mockRejectedValue(
      new ApiRequestError(502, "No se pudo generar la respuesta."),
    );

    render(<KnowledgePage />);
    await userEvent.type(screen.getByLabelText("Pregunta"), "¿SLA express?");
    await userEvent.click(screen.getByRole("button", { name: "Consultar" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "El asistente no está disponible ahora mismo",
      );
    });
    expect(screen.queryByText("Respuesta")).not.toBeInTheDocument();
  });

  it("valida que la pregunta no esté vacía", async () => {
    render(<KnowledgePage />);
    await userEvent.click(screen.getByRole("button", { name: "Consultar" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Escribe una pregunta",
    );
    expect(mockAskKnowledge).not.toHaveBeenCalled();
  });
});
