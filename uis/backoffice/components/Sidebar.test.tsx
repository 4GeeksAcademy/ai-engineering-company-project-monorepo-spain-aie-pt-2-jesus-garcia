import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "@/components/Sidebar";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children?: React.ReactNode;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { email: "ops@trackflow.com" },
    logout: vi.fn(),
  }),
}));

describe("Sidebar", () => {
  it("incluye la entrada de Inventario enlazando a /inventory", () => {
    render(<Sidebar />);

    const link = screen.getByRole("link", { name: /Inventario/ });
    expect(link).toHaveAttribute("href", "/inventory");
  });
});