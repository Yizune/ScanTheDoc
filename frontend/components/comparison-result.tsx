"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useMemo, useRef, useState } from "react";
import type {
  PdfComparisonChange,
  PdfHighlight,
  PdfPageInfo,
} from "@/lib/types";

const API_URL = "/backend";

type ComparedDocument = {
  id: string;
  name: string;
  pages: PdfPageInfo[];
};

export type ComparisonResultValue = {
  changes: PdfComparisonChange[];
  changesTruncated: boolean;
  compared: ComparedDocument;
  original: ComparedDocument;
  similarityPercent: number;
};

type PositionedHighlight = PdfHighlight & {
  changeId: string;
  tone: "added" | "removed";
};

type DisplayChange = {
  key: string;
  kind: PdfComparisonChange["kind"];
  page: number;
};

export function ComparisonResult({
  result,
  onClose,
}: {
  result: ComparisonResultValue;
  onClose: () => void;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const originalScroll = useRef<HTMLDivElement>(null);
  const comparedScroll = useRef<HTMLDivElement>(null);
  const [reversed, setReversed] = useState(false);
  const originalSources = usePagePreviews(result.original);
  const comparedSources = usePagePreviews(result.compared);
  const original = reversed ? result.compared : result.original;
  const compared = reversed ? result.original : result.compared;
  const visibleOriginalSources = reversed ? comparedSources : originalSources;
  const visibleComparedSources = reversed ? originalSources : comparedSources;
  const visibleChanges = useMemo(
    () => (reversed ? result.changes.map(reverseChange) : result.changes),
    [result.changes, reversed],
  );
  const pageNumbers = useMemo(
    () =>
      Array.from(
        new Set([
          ...original.pages.map((page) => page.page),
          ...compared.pages.map((page) => page.page),
        ]),
      ).sort((first, second) => first - second),
    [compared.pages, original.pages],
  );
  const displayChanges = useMemo<DisplayChange[]>(
    () => {
      const originalPages = new Set(original.pages.map((page) => page.page));
      const comparedPages = new Set(compared.pages.map((page) => page.page));
      const changedPages = new Set(visibleChanges.flatMap(changePages));

      return pageNumbers.flatMap((page) => {
        let kind: PdfComparisonChange["kind"] | null = null;
        if (!originalPages.has(page)) kind = "added";
        else if (!comparedPages.has(page)) kind = "removed";
        else if (changedPages.has(page)) kind = "replaced";

        return kind ? [{ key: `page-${page}`, kind, page }] : [];
      });
    },
    [compared.pages, original.pages, pageNumbers, visibleChanges],
  );

  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    closeButton.current?.focus();

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }

    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
      previousFocus?.focus();
    };
  }, [onClose]);

  function openPage(page: number) {
    scrollPaneToPage(originalScroll.current, page);
    scrollPaneToPage(comparedScroll.current, page);
  }

  return (
    <div className="comparison-backdrop">
      <section
        aria-labelledby="comparison-title"
        aria-modal="true"
        className="comparison-viewer"
        role="dialog"
      >
        <header className="comparison-toolbar">
          <div>
            <h2 id="comparison-title">Comparison result</h2>
            <p className="comparison-file-names">
              <strong className="comparison-file-name">{original.name}</strong>
              <span className="comparison-file-role">Original</span>
              <button
                className="comparison-switch"
                type="button"
                onClick={() => setReversed((current) => !current)}
              >
                Switch
              </button>
              <strong className="comparison-file-name comparison-file-name-second">
                {compared.name}
              </strong>
              <span className="comparison-file-role">New version</span>
            </p>
          </div>
          <div className="comparison-summary">
            <span>
              <strong className="comparison-summary-value">
                {result.similarityPercent}%
              </strong>{" "}
              similar
            </span>
            <span>
              <strong className="comparison-summary-value">
                {displayChanges.length}
              </strong>{" "}
              {displayChanges.length === 1 ? "changed page" : "changed pages"}
            </span>
          </div>
          <button
            aria-label="Close comparison"
            className="comparison-close"
            ref={closeButton}
            type="button"
            onClick={onClose}
          >
            {"\u00d7"}
          </button>
        </header>

        <div className="comparison-layout">
          <nav aria-label="Changed pages" className="comparison-thumbnails">
            {pageNumbers.map((pageNumber) => {
              const originalPage = findPage(original.pages, pageNumber);
              const comparedPage = findPage(compared.pages, pageNumber);
              const hasBothPages = originalPage && comparedPage;
              return (
                <button
                  className="comparison-thumbnail"
                  key={pageNumber}
                  type="button"
                  onClick={() => openPage(pageNumber)}
                >
                  <span
                    className={`comparison-thumbnail-images${hasBothPages ? "" : " single"}`}
                  >
                    {originalPage && (
                      <Thumbnail
                        page={originalPage}
                        source={visibleOriginalSources.get(pageNumber)}
                      />
                    )}
                    {comparedPage && (
                      <Thumbnail
                        page={comparedPage}
                        source={visibleComparedSources.get(pageNumber)}
                      />
                    )}
                  </span>
                  <span>Page {pageNumber}</span>
                </button>
              );
            })}
          </nav>

          <div className="comparison-panes">
            <DocumentPane
              changes={visibleChanges}
              document={original}
              label="Original"
              paneRef={originalScroll}
              side="original"
              sources={visibleOriginalSources}
            />
            <DocumentPane
              changes={visibleChanges}
              document={compared}
              label="New version"
              paneRef={comparedScroll}
              side="compared"
              sources={visibleComparedSources}
            />
          </div>

          <aside className="comparison-changes">
            <header>
              <strong>Changes</strong>
            </header>
            <div className="comparison-change-list">
              {displayChanges.length ? (
                displayChanges.map((item) => (
                  <button
                    className="comparison-change"
                    key={item.key}
                    type="button"
                    onClick={() => openPage(item.page)}
                  >
                    <span className="comparison-change-page">
                      Page {item.page}
                    </span>
                    <strong className="comparison-change-kind">
                      {changeLabel(item.kind)}
                    </strong>
                  </button>
                ))
              ) : (
                <p className="comparison-empty">No text changes found.</p>
              )}
              {result.changesTruncated && (
                <p className="comparison-truncated">
                  Showing the first 200 changes.
                </p>
              )}
            </div>
          </aside>
        </div>
      </section>
    </div>
  );
}

function DocumentPane({
  changes,
  document,
  label,
  paneRef,
  side,
  sources,
}: {
  changes: PdfComparisonChange[];
  document: ComparedDocument;
  label: string;
  paneRef: React.RefObject<HTMLDivElement | null>;
  side: "compared" | "original";
  sources: Map<number, string>;
}) {
  const highlightsByPage = useMemo(() => {
    const pages = new Map<number, PositionedHighlight[]>();
    for (const change of changes) {
      const highlights =
        side === "original"
          ? change.original_highlights
          : change.compared_highlights;
      for (const highlight of highlights) {
        const pageHighlights = pages.get(highlight.page) ?? [];
        pageHighlights.push({
          ...highlight,
          changeId: change.id,
          tone: side === "original" ? "removed" : "added",
        });
        pages.set(highlight.page, pageHighlights);
      }
    }
    return pages;
  }, [changes, side]);

  return (
    <section className="comparison-pane">
      <header>
        <span className="comparison-pane-label">{label}</span>
        <strong className="comparison-pane-name">{document.name}</strong>
      </header>
      <div className="comparison-page-scroll" ref={paneRef}>
        {document.pages.map((page) => (
          <PdfPage
            highlights={highlightsByPage.get(page.page) ?? []}
            key={page.page}
            page={page}
            source={sources.get(page.page)}
          />
        ))}
      </div>
    </section>
  );
}

function PdfPage({
  highlights,
  page,
  source,
}: {
  highlights: PositionedHighlight[];
  page: PdfPageInfo;
  source?: string;
}) {
  return (
    <article
      className="comparison-page"
      data-page={page.page}
      style={{ aspectRatio: `${page.width} / ${page.height}` }}
    >
      {source ? (
        <img
          alt={`Page ${page.page}`}
          className="comparison-page-image"
          src={source}
        />
      ) : (
        <div aria-hidden="true" className="comparison-page-loading" />
      )}
      {highlights.map((highlight) => (
        <span
          className={`comparison-highlight comparison-highlight-${highlight.tone}`}
          data-change-id={highlight.changeId}
          key={`${highlight.changeId}-${highlight.x}-${highlight.y}`}
          style={{
            height: `${(highlight.height / page.height) * 100}%`,
            left: `${(highlight.x / page.width) * 100}%`,
            top: `${(highlight.y / page.height) * 100}%`,
            width: `${(highlight.width / page.width) * 100}%`,
          }}
        />
      ))}
      <span className="comparison-page-number">{page.page}</span>
    </article>
  );
}

function Thumbnail({ page, source }: { page: PdfPageInfo; source?: string }) {
  return (
    <span
      className="comparison-thumbnail-image"
      style={{ aspectRatio: `${page.width} / ${page.height}` }}
    >
      {source && <img alt="" src={source} />}
    </span>
  );
}

function usePagePreviews(document: ComparedDocument) {
  const { getToken } = useAuth();
  const getTokenRef = useRef(getToken);
  const [sources, setSources] = useState<Map<number, string>>(new Map());

  useEffect(() => {
    getTokenRef.current = getToken;
  }, [getToken]);

  useEffect(() => {
    let active = true;
    const objectUrls = new Set<string>();
    const controller = new AbortController();
    const pages = [...document.pages];

    setSources(new Map());

    async function loadPage(page: PdfPageInfo, token: string | null) {
      for (let attempt = 1; attempt <= 4 && active; attempt += 1) {
        try {
          const response = await fetch(
            `${API_URL}/api/v1/documents/${document.id}/pages/${page.page}/preview`,
            {
              headers: token
                ? { Authorization: `Bearer ${token}` }
                : undefined,
              signal: controller.signal,
            },
          );
          if (!response.ok) throw new Error("Page preview failed");

          const objectUrl = URL.createObjectURL(await response.blob());
          if (!active) {
            URL.revokeObjectURL(objectUrl);
            return;
          }

          objectUrls.add(objectUrl);
          setSources((current) =>
            new Map(current).set(page.page, objectUrl),
          );
          return;
        } catch {
          if (!active || controller.signal.aborted) return;
          await new Promise((resolve) =>
            window.setTimeout(resolve, attempt * 250),
          );
        }
      }
    }

    async function loadPages() {
      const token = await getTokenRef.current();
      await Promise.all(
        Array.from({ length: Math.min(4, pages.length) }, async () => {
          while (active) {
            const page = pages.shift();
            if (!page) return;
            await loadPage(page, token);
          }
        }),
      );
    }

    loadPages().catch(() => undefined);
    return () => {
      active = false;
      controller.abort();
      for (const objectUrl of objectUrls) URL.revokeObjectURL(objectUrl);
    };
  }, [document.id, document.pages]);

  return sources;
}

function findPage(pages: PdfPageInfo[], pageNumber: number) {
  return pages.find((page) => page.page === pageNumber);
}

function changePages(change: PdfComparisonChange) {
  return Array.from(
    new Set(
      [...change.original_highlights, ...change.compared_highlights].map(
        (highlight) => highlight.page,
      ),
    ),
  ).sort((first, second) => first - second);
}

function scrollPaneToPage(pane: HTMLDivElement | null, page: number) {
  const target = pane?.querySelector<HTMLElement>(`[data-page="${page}"]`);
  target?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function changeLabel(kind: PdfComparisonChange["kind"]) {
  if (kind === "added") return "Added";
  if (kind === "removed") return "Removed";
  return "Changed";
}

function reverseChange(change: PdfComparisonChange): PdfComparisonChange {
  return {
    ...change,
    kind:
      change.kind === "added"
        ? "removed"
        : change.kind === "removed"
          ? "added"
          : "replaced",
    original_text: change.compared_text,
    compared_text: change.original_text,
    original_highlights: change.compared_highlights,
    compared_highlights: change.original_highlights,
  };
}
