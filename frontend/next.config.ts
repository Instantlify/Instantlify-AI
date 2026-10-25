import type { NextConfig } from "next";

const backend = process.env.BACKEND_INTERNAL_URL || "http://127.0.0.1:8000";
const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: "/api/:path*/", destination: `${backend}/api/:path*/` },
      { source: "/health/:path*/", destination: `${backend}/health/:path*/` },
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
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
};
export default nextConfig;
