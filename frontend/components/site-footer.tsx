"use client";

import { useEffect, useState } from "react";

export function SiteFooter() {
  const [year, setYear] = useState(() => new Date().getFullYear());

  useEffect(() => {
    const timer = window.setInterval(
      () => {
        setYear(new Date().getFullYear());
      },
      60 * 60 * 1000,
    );

    return () => window.clearInterval(timer);
  }, []);

  return (
    <footer className="site-footer">
      <p>
        © <time dateTime={String(year)}>{year}</time>{" "}
        <a
          className="footer-author"
          href="https://stevan-dev.vercel.app/"
          target="_blank"
          rel="noreferrer"
        >
          Stevan Likušić
        </a>
        . All rights reserved.
      </p>
    </footer>
  );
}
