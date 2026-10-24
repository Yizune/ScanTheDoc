import type { ReactNode } from "react";
import { ClerkAppProvider } from "@/components/clerk-app-provider";

export default function ToolLayout({ children }: { children: ReactNode }) {
  return <ClerkAppProvider>{children}</ClerkAppProvider>;
}
