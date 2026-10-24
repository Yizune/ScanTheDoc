import { ClerkProvider } from "@clerk/nextjs";
import type { ReactNode } from "react";

export function ClerkAppProvider({ children }: { children: ReactNode }) {
  return (
    <ClerkProvider
      signInUrl="/sign-in"
      signUpUrl="/sign-up"
      afterSignOutUrl="/"
    >
      {children}
    </ClerkProvider>
  );
}
