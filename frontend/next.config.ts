import type { NextConfig } from "next";

const backend = process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000";
const nextConfig: NextConfig = {
  output: "standalone",
  allowedDevOrigins: ["127.0.0.1"],
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: "/api/:path*/", destination: `${backend}/api/:path*/` },
      {
        source: "/webhooks/:path*/",
        destination: `${backend}/webhooks/:path*/`,
      },
      { source: "/health/:path*/", destination: `${backend}/health/:path*/` },
      // OAuth discovery for the MCP connector (claude.ai), served by the backend.
      {
        source: "/.well-known/:path*",
        destination: `${backend}/.well-known/:path*`,
      },
      { source: "/go/:code/", destination: `${backend}/go/:code/` },
      { source: "/r/:code/", destination: `${backend}/r/:code/` },
    ];
  },
  trailingSlash: true,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
      {
        source: "/f/:slug/",
        headers: [
          { key: "Content-Security-Policy", value: "frame-ancestors *" },
        ],
      },
    ];
  },
};
export default nextConfig;
