import path from "node:path";
import type { NextConfig } from "next";

const apiUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const wsUrl = apiUrl.replace(/^http/, "ws");
const isDev = process.env.NODE_ENV !== "production";

const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self' ${apiUrl} ${wsUrl}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "Content-Security-Policy", value: csp },
];

const nextConfig: NextConfig = {
  turbopack: {
    root: path.resolve(process.cwd(), "..", ".."),
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
  async rewrites() {
    const backend = process.env.BACKEND_URL ?? "http://localhost:8000";
    return [
      {
        source: "/api/incidents/:path*",
        destination: `${backend}/api/incidents/:path*`,
      },
      {
        source: "/api/rfp/:path*",
        destination: `${backend}/rfp/:path*`,
      },
      {
        source: "/api/realtime/:path*",
        destination: `${backend}/realtime/:path*`,
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
        source: "/api/telemetry/:path*",
        destination: `${backend}/telemetry/:path*`,
      },
      {
        source: "/api/tasks/:path*",
        destination: `${backend}/tasks/:path*`,
      },
      {
        source: "/api/reporting/:path*",
        destination: `${backend}/reporting/:path*`,
      },
      {
        source: "/api/knowledge/:path*",
        destination: `${backend}/knowledge/:path*`,
      },
      {
        source: "/api/chat/:path*",
        destination: `${backend}/chat/:path*`,
      },
      {
        source: "/api/users",
        destination: `${backend}/api/users`,
      },
    ];
  },
};

export default nextConfig;
