import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
    return [
      {
        source: "/api/incidents/:path*",
        destination: `${backend}/api/incidents/:path*`,
      },
    ];
  },
};

export default nextConfig;
