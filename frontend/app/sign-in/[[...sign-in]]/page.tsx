import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <main className="auth-page">
      <section className="auth-box">
        <div className="auth-heading">
          <strong>ScanTheDoc</strong>
          <p>Sign in to manage your documents.</p>
        </div>
        <SignIn
          routing="path"
          path="/sign-in"
          signUpUrl="/sign-up"
          fallbackRedirectUrl="/tool"
        />
      </section>
    </main>
  );
}
