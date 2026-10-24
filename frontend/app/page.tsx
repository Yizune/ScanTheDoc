import { AccountActions, LandingActions } from "@/components/account-actions";
import { ClerkAppProvider } from "@/components/clerk-app-provider";
import { SiteFooter } from "@/components/site-footer";

export default function Home() {
  return (
    <ClerkAppProvider>
      <main className="workspace">
        <header className="topbar">
          <a className="brand" href="#top">
            ScanTheDoc
          </a>
          <AccountActions />
        </header>

        <section className="landing-hero" id="top">
          <div>
            <h1>Useful tools for PDFs and scanned documents.</h1>
            <p>
              Upload a PDF or image to read its text, search it, compare
              documents, merge PDFs, or work with individual pages.
            </p>
            <LandingActions />
          </div>
        </section>

        <SiteFooter />
      </main>
    </ClerkAppProvider>
  );
}
