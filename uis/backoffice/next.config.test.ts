import { describe, expect, it } from "vitest";
import nextConfig from "@/next.config";

interface RewriteRule {
  source: string;
  destination: string;
}

async function getInventoryRewrite(): Promise<RewriteRule> {
  const rewrites = (await nextConfig.rewrites!()) as RewriteRule[];
  const rule = rewrites.find((r) => r.source === "/api/inventory/:path*");
  if (!rule) throw new Error("No se encontró el rewrite de /api/inventory/:path*");
  return rule;
}

const DEFAULT_BACKEND = "http://localhost:8000";

describe("rewrite de inventario", () => {
  it("existe una regla para /api/inventory/:path*", async () => {
    const rule = await getInventoryRewrite();
    expect(rule.source).toBe("/api/inventory/:path*");
  });

  it("reenvía al backend bajo /inventory (sin el segmento /api)", async () => {
    const rule = await getInventoryRewrite();
    expect(rule.destination).toBe(`${DEFAULT_BACKEND}/inventory/:path*`);
  });
});