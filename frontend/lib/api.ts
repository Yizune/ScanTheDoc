"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback } from "react";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export function useApi() {
  const { getToken } = useAuth();

  return useCallback(
    async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
      const token = await getToken();
      const headers = new Headers(init.headers);
      if (token) headers.set("Authorization", `Bearer ${token}`);
      if (init.body && !(init.body instanceof FormData)) {
        headers.set("Content-Type", "application/json");
      }

      const response = await fetch(path, {
        ...init,
        headers,
        cache: "no-store",
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new ApiError(body?.detail ?? "Request failed", response.status);
      }
      return response.status === 204 ? (undefined as T) : response.json();
    },
    [getToken],
  );
}
