import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    root: path.resolve(process.cwd(), "..", ".."),
  },
  async rewrites() {
    const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
    return [
      {
        source: "/api/incidents/:path*",
        destination: `${backend}/api/incidents/:path*`,
      },
      {
        source: "/api/suppliers/:path*",
        destination: `${backend}/api/suppliers/:path*`,
      },
      {
        source: "/api/inventory/:path*",
        destination: `${backend}/inventory/:path*`,
      },
      {
        source: "/api/auth/:path*",
        destination: `${backend}/api/auth/:path*`,
      },
      {
        source: "/api/users",
        destination: `${backend}/api/users`,
      },
    ];
  },
};

export default nextConfig;
