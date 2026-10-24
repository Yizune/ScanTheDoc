import { existsSync } from "node:fs";
import path from "node:path";
import { loadEnvFile } from "node:process";
import type { NextConfig } from "next";

const rootEnvFile = path.resolve(process.cwd(), "../.env");

if (existsSync(rootEnvFile)) {
  loadEnvFile(rootEnvFile);
}

const apiTarget = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  agentRules: false,
  reactStrictMode: true,
  turbopack: {
    root: process.cwd(),
  },
  async rewrites() {
    return [
      {
        source: "/backend/:path*",
        destination: `${apiTarget}/:path*`,
      },
    ];
  },
};

export default nextConfig;
