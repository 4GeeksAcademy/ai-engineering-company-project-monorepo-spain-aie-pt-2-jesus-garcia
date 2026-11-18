import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApprovalPanel } from "@/components/rfp/ApprovalPanel";
import * as api from "@/lib/api";
import type { RfpApprovals } from "@/lib/rfp-types";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    submitRfpApproval: vi.fn(),
  };
});

const mockSubmit = vi.mocked(api.submitRfpApproval);

const approvals: RfpApprovals = {
  ticket_id: "t1",
  rfp_id: "RFP-1",
  status: "esperando_aprobación",
  approval_status: "pending",
  thread_id: "rfp-t1:run-1",
  run: 1,
  max_rounds: 2,
  pending: [
    {
      department_id: "warehouse",
      department_label: "Warehouse Operations",
      responsible: "Ana Whitfield",
      approval_status: "pending_approval",
      approval_round: 0,
      interrupt_id: "interrupt-1",
      provisional: false,
      packet: {
        section_markdown: "# Propuesta de Almacenamiento\n\nContenido de la sección.",
        client: { name: "ModaViva, S.L." },
        client_country: "Spain",
        currency: "EUR",
        deadline: "2026-08-28",
        approval_round: 0,
        max_rounds: 2,
        allowed_actions: ["approve", "reject", "request_changes"],
        evaluation: {
          readability: { pass: true, score: 60 },
          relevance: { pass: true },
          compliance: { pass: true, rule_ids: [], violations: [] },
          overall_pass: true,
        },
        open_questions: ["Falta el volumen mensual de pedidos."],
        conflicts: [],
      },
    },
  ],
  decisions: [],
  final_document_ready: false,
};

const onSubmitted = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  mockSubmit.mockResolvedValue({
    ticket_id: "t1",
    task_id: "task-1",
    department_id: "warehouse",
    action: "approve",
    status: "esperando_aprobación",
    pending_remaining: 1,
  });
});

describe("ApprovalPanel", () => {
  it("muestra el paquete mínimo y aprueba con el responsable nombrado", async () => {
    const user = userEvent.setup();
    render(
      <ApprovalPanel
        ticketId="t1"
        token="token"
        approvals={approvals}
        onSubmitted={onSubmitted}
      />,
    );

    expect(screen.getByText("Warehouse Operations")).toBeInTheDocument();
    expect(screen.getAllByText("Ana Whitfield", { exact: false }).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Contenido de la sección/).length).toBeGreaterThan(0);
    expect(screen.getByText(/volumen mensual/)).toBeInTheDocument();
    expect(screen.getByText("ModaViva, S.L.", { exact: false })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Aprobar sección" }));

    await waitFor(() => expect(mockSubmit).toHaveBeenCalledTimes(1));
    expect(mockSubmit).toHaveBeenCalledWith(
      "t1",
      "warehouse",
      expect.objectContaining({
        action: "approve",
        approver: "Ana Whitfield",
        interrupt_id: "interrupt-1",
      }),
      "token",
    );
    expect(onSubmitted).toHaveBeenCalled();
  });

  it("exige comentario al rechazar y confirma antes de enviar", async () => {
    const user = userEvent.setup();
    render(
      <ApprovalPanel
        ticketId="t1"
        token="token"
        approvals={approvals}
        onSubmitted={onSubmitted}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Rechazar sección" }));
    expect(
      screen.getByText(/Rechazar o solicitar cambios exige un comentario/),
    ).toBeInTheDocument();
    expect(mockSubmit).not.toHaveBeenCalled();

    await user.type(
      screen.getByLabelText(/Comentario de la decisión/i),
      "Falta confirmar la capacidad.",
    );
    await user.click(screen.getByRole("button", { name: "Rechazar sección" }));
    expect(
      screen.getByText("Rechazar la sección"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Rechazar" }));

    await waitFor(() => expect(mockSubmit).toHaveBeenCalledTimes(1));
    expect(mockSubmit).toHaveBeenCalledWith(
      "t1",
      "warehouse",
      expect.objectContaining({
        action: "reject",
        comment: "Falta confirmar la capacidad.",
      }),
      "token",
    );
  });

  it("exige aceptación explícita en una sección provisional", async () => {
    const user = userEvent.setup();
    render(
      <ApprovalPanel
        ticketId="t1"
        token="token"
        approvals={{
          ...approvals,
          pending: [
            {
              ...approvals.pending[0],
              provisional: true,
              packet: {
                ...approvals.pending[0].packet,
                provisional: true,
              },
            },
          ],
        }}
        onSubmitted={onSubmitted}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Aprobar sección" }));
    expect(
      screen.getByText(/marca la casilla de aceptación/),
    ).toBeInTheDocument();
    expect(mockSubmit).not.toHaveBeenCalled();

    await user.click(
      screen.getByRole("checkbox", {
        name: /Acepto explícitamente el borrador provisional/i,
      }),
    );
    await user.type(
      screen.getByLabelText(/Comentario de la decisión/i),
      "Revisado con Ana.",
    );
    await user.click(screen.getByRole("button", { name: "Aprobar sección" }));

    await waitFor(() => expect(mockSubmit).toHaveBeenCalledTimes(1));
    expect(mockSubmit).toHaveBeenCalledWith(
      "t1",
      "warehouse",
      expect.objectContaining({
        action: "approve",
        acknowledge_provisional: true,
        comment: "Revisado con Ana.",
      }),
      "token",
    );
  });
});
