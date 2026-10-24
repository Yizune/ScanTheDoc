import { existsSync } from "node:fs";
import path from "node:path";
import { loadEnvFile } from "node:process";
import type { NextConfig } from "next";

const rootEnvFile = path.resolve(process.cwd(), "../.env");

if (existsSync(rootEnvFile)) {
  loadEnvFile(rootEnvFile);
}

const nextConfig: NextConfig = {
  agentRules: false,
  reactStrictMode: true,
  turbopack: {
    root: process.cwd(),
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/api/:path*",
      },
    ];
  },
};

export default nextConfig;
