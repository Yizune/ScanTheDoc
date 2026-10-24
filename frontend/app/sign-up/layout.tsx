import type { ReactNode } from "react";
import { ClerkAppProvider } from "@/components/clerk-app-provider";

export default function SignUpLayout({ children }: { children: ReactNode }) {
  return <ClerkAppProvider>{children}</ClerkAppProvider>;
}
