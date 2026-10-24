import { clerkMiddleware } from "@clerk/nextjs/server";

export default clerkMiddleware();

export const config = {
  matcher: ["/", "/tool/:path*", "/sign-in/:path*", "/sign-up/:path*"],
};
