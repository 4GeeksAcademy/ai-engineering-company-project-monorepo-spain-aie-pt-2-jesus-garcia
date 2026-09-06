import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

function SmokeComponent({ label }: { label: string }) {
  return <span>Vitest + RTL listo para {label}</span>;
}

describe("infraestructura de tests", () => {
  it("renderiza un componente con Testing Library", () => {
    render(<SmokeComponent label="inventario" />);
    expect(screen.getByText("Vitest + RTL listo para inventario")).toBeInTheDocument();
  });
});