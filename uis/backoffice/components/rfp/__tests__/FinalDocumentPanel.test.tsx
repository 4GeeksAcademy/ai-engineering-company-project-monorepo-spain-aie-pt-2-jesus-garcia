import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FinalDocumentPanel } from "@/components/rfp/FinalDocumentPanel";
import * as api from "@/lib/api";
import type { RfpFinalDocument } from "@/lib/rfp-types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    downloadRfpFinalDocument: vi.fn(),
  };
});

const mockDownload = vi.mocked(api.downloadRfpFinalDocument);

const document: RfpFinalDocument = {
  contract_version: "rfp-final-v1",
  ticket_id: "t1",
  currency: "EUR",
  sections: [],
  approved_by: [
    {
      department_id: "warehouse",
      department_label: "Warehouse Operations",
      responsible: "Ana Whitfield",
      approver: "Ana Whitfield",
      approved_at: "2026-11-15T12:00:00+00:00",
      comment: "Capacidad validada.",
      provisional: false,
    },
  ],
  markdown: "# Propuesta comercial\n\nContenido final.",
  document_path: "/tmp/propuesta-final.md",
  generated_at: "2026-11-15T12:05:00+00:00",
};

beforeEach(() => {
  vi.clearAllMocks();
  mockDownload.mockResolvedValue(new Blob(["# Propuesta"], { type: "text/markdown" }));
  Object.defineProperty(window.URL, "createObjectURL", {
    writable: true,
    value: vi.fn(() => "blob:propuesta"),
  });
  Object.defineProperty(window.URL, "revokeObjectURL", {
    writable: true,
    value: vi.fn(),
  });
  Object.defineProperty(HTMLAnchorElement.prototype, "click", {
    writable: true,
    value: vi.fn(),
  });
});

describe("FinalDocumentPanel", () => {
  it("muestra el documento y las aprobaciones", () => {
    render(<FinalDocumentPanel ticketId="t1" token="token" document={document} />);

    expect(screen.getByText("Documento final acordado")).toBeInTheDocument();
    expect(screen.getByText(/Contenido final/)).toBeInTheDocument();
    expect(screen.getAllByText("Ana Whitfield").length).toBeGreaterThan(0);
    expect(screen.getByText("Capacidad validada.")).toBeInTheDocument();
  });

  it("descarga el Markdown con el token", async () => {
    const user = userEvent.setup();
    render(<FinalDocumentPanel ticketId="t1" token="token" document={document} />);

    await user.click(screen.getByRole("button", { name: "Descargar Markdown" }));

    await waitFor(() => expect(mockDownload).toHaveBeenCalledWith("t1", "token"));
    expect(window.URL.createObjectURL).toHaveBeenCalled();
  });
});
