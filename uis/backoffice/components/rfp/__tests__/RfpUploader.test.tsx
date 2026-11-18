import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RfpUploader } from "@/components/rfp/RfpUploader";
import * as api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    uploadRfp: vi.fn(),
  };
});

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

const mockUpload = vi.mocked(api.uploadRfp);
const mockUseAuth = vi.mocked(useAuth);

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

describe("Recepción de RFPs — uploader", () => {
  it("crea un ticket por cada PDF seleccionado", async () => {
    mockUpload
      .mockResolvedValueOnce({
        ticket_id: "t1",
        rfp_id: "RFP-2026-0001",
        status: "analizando",
        task_id: "task-1",
      })
      .mockResolvedValueOnce({
        ticket_id: "t2",
        rfp_id: "RFP-2026-0002",
        status: "analizando",
        task_id: "task-2",
      });
    const onUploaded = vi.fn();

    render(<RfpUploader onUploaded={onUploaded} />);

    const input = screen.getByLabelText("Subir RFPs en PDF");
    const files = [
      new File(["%PDF-1.4"], "modaviva.pdf", { type: "application/pdf" }),
      new File(["%PDF-1.4"], "luna.pdf", { type: "application/pdf" }),
    ];
    fireEvent.change(input, { target: { files } });

    await waitFor(() => expect(mockUpload).toHaveBeenCalledTimes(2));
    expect(mockUpload).toHaveBeenNthCalledWith(1, files[0], "test-token");
    expect(mockUpload).toHaveBeenNthCalledWith(2, files[1], "test-token");
    await waitFor(() => expect(onUploaded).toHaveBeenCalledTimes(1));
    expect(screen.getByText(/RFP-2026-0001/)).toBeInTheDocument();
    expect(screen.getByText(/RFP-2026-0002/)).toBeInTheDocument();
  });

  it("rechaza archivos que no son PDF sin llamar al backend", async () => {
    render(<RfpUploader onUploaded={vi.fn()} />);

    const input = screen.getByLabelText("Subir RFPs en PDF");
    fireEvent.change(input, {
      target: {
        files: [new File(["hola"], "notas.txt", { type: "text/plain" })],
      },
    });

    await waitFor(() =>
      expect(screen.getByText(/Solo se aceptan archivos PDF/)).toBeInTheDocument(),
    );
    expect(mockUpload).not.toHaveBeenCalled();
  });
});
