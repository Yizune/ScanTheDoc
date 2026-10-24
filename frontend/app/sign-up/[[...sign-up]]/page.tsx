import { SignUp } from "@clerk/nextjs";

export default function SignUpPage() {
  return (
    <main className="auth-page">
      <section className="auth-box">
        <div className="auth-heading">
          <strong>ScanTheDoc</strong>
          <p>Create an account to manage your documents.</p>
        </div>
        <SignUp
          routing="path"
          path="/sign-up"
          signInUrl="/sign-in"
          fallbackRedirectUrl="/tool"
        />
      </section>
    </main>
  );
}
