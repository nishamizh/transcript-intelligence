import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Dev JS is served only to localhost unless the host is listed here.
  // The briefing is opened at 127.0.0.1 and at the cloud-agent hostname.
  allowedDevOrigins: ["127.0.0.1", "*.agent.cvm.dev"],
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
