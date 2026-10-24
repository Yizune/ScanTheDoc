"use client";

import { UserButton, useAuth } from "@clerk/nextjs";
import Link from "next/link";

export function AccountActions() {
  const { isLoaded, isSignedIn } = useAuth();

  if (!isLoaded) return <div className="topbar-actions" />;

  return (
    <div className="topbar-actions">
      {!isSignedIn ? (
        <>
          <Link className="text-link" href="/sign-in">
            Sign in
          </Link>
          <Link className="small-button" href="/sign-up">
            Create account
          </Link>
        </>
      ) : (
        <div className="account-control">
          <UserButton showName />
        </div>
      )}
    </div>
  );
}

export function LandingActions() {
  const { isLoaded, isSignedIn } = useAuth();

  return (
    <>
      <div className="hero-actions">
        <Link className="primary-link" href="/tool">
          {isLoaded && isSignedIn ? "Open workspace" : "Use ScanTheDoc"}
        </Link>
        {isLoaded && !isSignedIn && (
          <Link className="secondary-link" href="/sign-up">
            Create an account
          </Link>
        )}
      </div>
      {isLoaded && (
        <p className="guest-note">
          Files in the public workspace are visible to everyone. Sign in for a
          private workspace.
        </p>
      )}
    </>
  );
}
