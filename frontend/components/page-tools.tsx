"use client";

import { type FormEvent, useState } from "react";

type PageToolsProps = {
  pageCount: number;
  working: string;
  onClose: () => void;
  onExtract: (pages: string, name: string) => void;
  onSplit: () => void;
};

export function PageTools({
  pageCount,
  working,
  onClose,
  onExtract,
  onSplit,
}: PageToolsProps) {
  const [pages, setPages] = useState("");
  const [name, setName] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onExtract(pages, name);
  }

  return (
    <div className="dialog-backdrop">
      <section
        aria-labelledby="page-tools-title"
        aria-modal="true"
        className="page-tools-dialog"
        role="dialog"
      >
        <header>
          <h2 id="page-tools-title">Page tools</h2>
          <button
            aria-label="Close page tools"
            className="page-tools-close"
            type="button"
            disabled={!!working}
            onClick={onClose}
          >
            &times;
          </button>
        </header>

        <form className="page-tools-form" onSubmit={handleSubmit}>
          <h3>Extract selected pages</h3>
          <p>
            Enter one page (1), separate pages with commas (1, 3, 5), or use a
            page range (1-4).
          </p>
          <label htmlFor="page-selection">Pages to include</label>
          <input
            autoFocus
            className="page-tools-input"
            id="page-selection"
            value={pages}
            placeholder="Enter pages..."
            required
            onChange={(event) => setPages(event.target.value)}
          />
          <label htmlFor="page-result-name">New document name</label>
          <input
            className="page-tools-input"
            id="page-result-name"
            value={name}
            placeholder="Enter name..."
            required
            maxLength={255}
            onChange={(event) => setName(event.target.value)}
          />
          <button type="submit" disabled={!!working}>
            {working === "extract_pages" ? "Extracting..." : "Extract pages"}
          </button>
        </form>

        <div className="split-pages">
          <h3>Split every page</h3>
          <p>
            Create a separate PDF for each page.
            {pageCount < 2 && " This requires a PDF with at least 2 pages."}
          </p>
          <button
            type="button"
            disabled={!!working || pageCount < 2}
            onClick={onSplit}
          >
            {working === "split" ? "Splitting..." : "Split PDF"}
          </button>
        </div>
      </section>
    </div>
  );
}
