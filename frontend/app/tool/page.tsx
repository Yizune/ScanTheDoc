"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AccountActions } from "@/components/account-actions";
import {
  ComparisonResult,
  type ComparisonResultValue,
} from "@/components/comparison-result";
import { DocumentUpload } from "@/components/document-upload";
import { PageTools } from "@/components/page-tools";
import { SiteFooter } from "@/components/site-footer";
import {
  formatBytes,
  formatDate,
  formatFileType,
  StatusPill,
} from "@/components/ui";
import { errorMessage, useApi } from "@/lib/api";
import type { DocumentItem, ProcessingJob } from "@/lib/types";

export default function Home() {
  const api = useApi();
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [detail, setDetail] = useState<DocumentItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState("");
  const [sessionReady, setSessionReady] = useState(false);
  const [comparison, setComparison] = useState<ComparisonResultValue | null>(
    null,
  );
  const [pageToolsOpen, setPageToolsOpen] = useState(false);
  const [actionError, setActionError] = useState("");
  const [loadError, setLoadError] = useState("");
  const closeComparison = useCallback(() => setComparison(null), []);
  const closePageTools = useCallback(() => setPageToolsOpen(false), []);

  useEffect(() => {
    if (!isLoaded) return;

    let active = true;
    setSessionReady(false);

    async function prepareSession() {
      try {
        if (isSignedIn) {
          for (let attempt = 0; attempt < 20; attempt += 1) {
            if (!active) return;
            if (await getToken()) break;
            await new Promise((resolve) => window.setTimeout(resolve, 100));
          }
        }
      } finally {
        if (active) setSessionReady(true);
      }
    }

    prepareSession();
    return () => {
      active = false;
    };
  }, [getToken, isLoaded, isSignedIn]);

  const loadDocuments = useCallback(async () => {
    try {
      const data = await api<{ items: DocumentItem[] }>(
        `/api/v1/documents?q=${encodeURIComponent(query)}`,
      );
      setDocuments(data.items);
      setLoadError("");
    } catch (error) {
      setLoadError(errorMessage(error, "Could not load documents."));
    } finally {
      setLoading(false);
    }
  }, [api, query]);

  useEffect(() => {
    if (!sessionReady) return;
    const timer = setTimeout(loadDocuments, 250);
    return () => clearTimeout(timer);
  }, [loadDocuments, sessionReady]);

  useEffect(() => {
    if (!sessionReady) return;
    const timer = setInterval(loadDocuments, 3000);
    return () => clearInterval(timer);
  }, [loadDocuments, sessionReady]);

  const selectedDocuments = useMemo(
    () =>
      selected.flatMap((id) => {
        const document = documents.find((item) => item.id === id);
        return document ? [document] : [];
      }),
    [documents, selected],
  );
  const canMerge =
    selectedDocuments.length >= 2 &&
    selectedDocuments.every(
      (document) =>
        document.status === "ready" &&
        document.media_type === "application/pdf",
    );
  const canCompare =
    selectedDocuments.length === 2 &&
    selectedDocuments.every(
      (document) =>
        document.status === "ready" &&
        document.media_type === "application/pdf",
    );

  function toggleDocument(id: string) {
    setSelected((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id],
    );
  }

  async function waitForJob(jobId: string) {
    for (let attempt = 0; attempt < 80; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 750));
      const job = await api<ProcessingJob>(`/api/v1/jobs/${jobId}`);
      if (job.status === "completed") return job;
      if (job.status === "failed") {
        throw new Error(job.error_message || "Operation failed");
      }
    }
    throw new Error("The operation is taking longer than expected");
  }

  async function openDocument(id: string) {
    setWorking("open");
    setActionError("");
    try {
      setDetail(await api<DocumentItem>(`/api/v1/documents/${id}`));
    } catch (error) {
      setActionError(errorMessage(error, "Could not open document."));
    } finally {
      setWorking("");
    }
  }

  async function runTool(operation: "merge" | "compare") {
    const comparedDocuments =
      operation === "compare" ? selectedDocuments.slice(0, 2) : [];
    if (operation === "compare") setComparison(null);
    setWorking(operation);
    setActionError("");
    try {
      const job = await api<ProcessingJob>(`/api/v1/tools/${operation}`, {
        method: "POST",
        body: JSON.stringify(
          operation === "merge"
            ? { document_ids: selected, name: "Merged document" }
            : { document_ids: selected },
        ),
      });
      setSelected([]);
      const completed = await waitForJob(job.id);
      if (operation === "compare") {
        setComparison({
          changes: completed.result_data?.changes ?? [],
          changesTruncated: completed.result_data?.changes_truncated ?? false,
          compared: {
            id: comparedDocuments[1]?.id ?? "",
            name: comparedDocuments[1]?.name ?? "New version",
            pages: completed.result_data?.compared_pages ?? [],
          },
          original: {
            id: comparedDocuments[0]?.id ?? "",
            name: comparedDocuments[0]?.name ?? "Original",
            pages: completed.result_data?.original_pages ?? [],
          },
          similarityPercent: completed.result_data?.similarity_percent ?? 0,
        });
      } else {
        await loadDocuments();
        if (completed.result_document_id) {
          setDetail(
            await api<DocumentItem>(
              `/api/v1/documents/${completed.result_document_id}`,
            ),
          );
        }
      }
    } catch (error) {
      setActionError(errorMessage(error, "Operation failed."));
      await loadDocuments();
    } finally {
      setWorking("");
    }
  }

  async function downloadSelectedDocuments() {
    if (selectedDocuments.length === 0) return;
    setWorking("download");
    setActionError("");
    try {
      const token = await getToken();
      const singleDocument =
        selectedDocuments.length === 1 ? selectedDocuments[0] : null;
      const response = await fetch(
        singleDocument
          ? `/api/v1/documents/${singleDocument.id}/download`
          : "/api/v1/documents/download",
        {
          method: singleDocument ? "GET" : "POST",
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...(singleDocument ? {} : { "Content-Type": "application/json" }),
          },
          body: singleDocument
            ? undefined
            : JSON.stringify({ document_ids: selected }),
        },
      );
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? "Download failed");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = window.document.createElement("a");
      anchor.href = url;
      anchor.download = singleDocument
        ? singleDocument.original_filename
        : "ScanTheDoc documents.zip";
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setActionError(errorMessage(error, "Download failed."));
    } finally {
      setWorking("");
    }
  }

  async function runPageTool(
    operation: "extract_pages" | "split",
    pages?: string,
    name?: string,
  ) {
    if (!detail) return;
    setWorking(operation);
    setActionError("");
    try {
      const job = await api<ProcessingJob>(
        `/api/v1/documents/${detail.id}/${operation === "extract_pages" ? "extract-pages" : "split"}`,
        {
          method: "POST",
          body:
            operation === "extract_pages"
              ? JSON.stringify({ pages, name })
              : undefined,
        },
      );
      const completed = await waitForJob(job.id);
      await loadDocuments();
      setPageToolsOpen(false);
      if (completed.result_document_id) {
        setDetail(
          await api<DocumentItem>(
            `/api/v1/documents/${completed.result_document_id}`,
          ),
        );
      }
    } catch (error) {
      setActionError(errorMessage(error, "Page operation failed."));
      await loadDocuments();
    } finally {
      setWorking("");
    }
  }

  async function deleteSelectedDocuments() {
    if (selected.length === 0) return;
    const count = selected.length;
    if (
      !window.confirm(
        `Delete ${count} selected ${count === 1 ? "document" : "documents"}?`,
      )
    ) {
      return;
    }

    setWorking("delete_selected");
    setActionError("");
    try {
      const remaining: string[] = [];
      for (const documentId of selected) {
        try {
          await api(`/api/v1/documents/${documentId}`, { method: "DELETE" });
          if (detail?.id === documentId) setDetail(null);
        } catch {
          remaining.push(documentId);
        }
      }
      setSelected(remaining);
      if (remaining.length > 0) {
        setActionError("Some selected documents could not be deleted.");
      }
    } finally {
      await loadDocuments();
      setWorking("");
    }
  }

  return (
    <main className="workspace">
      <header className="topbar">
        <Link className="brand" href="/">
          ScanTheDoc
        </Link>
        <AccountActions />
      </header>

      <DocumentUpload
        onUploaded={loadDocuments}
        onError={setActionError}
      />

      {(actionError || loadError) && (
        <div className="workspace-error" role="alert">
          <span>{actionError || loadError}</span>
          <button
            className="text-button"
            type="button"
            onClick={() => {
              setActionError("");
              setLoadError("");
            }}
          >
            Dismiss
          </button>
        </div>
      )}

      <section className="document-section">
        <div className="document-toolbar">
          <input
            aria-label="Search documents"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search documents"
          />
        </div>

        <div className="selection-actions">
          <span>
            {documents.length}{" "}
            {documents.length === 1 ? "document" : "documents"}
            {selectedDocuments.length > 0 &&
              ` (${selectedDocuments.length} selected)`}
          </span>
          <button
            type="button"
            disabled={selected.length === 0 || !!working}
            onClick={downloadSelectedDocuments}
          >
            {working === "download" ? "Downloading..." : "Download"}
          </button>
          <button
            type="button"
            disabled={!canMerge || !!working}
            onClick={() => runTool("merge")}
          >
            {working === "merge" ? "Merging..." : "Merge PDFs"}
          </button>
          <button
            type="button"
            disabled={!canCompare || !!working}
            onClick={() => runTool("compare")}
          >
            {working === "compare" ? "Comparing..." : "Compare PDF versions"}
          </button>
          <button
            className="danger-button"
            type="button"
            disabled={selected.length === 0 || !!working}
            onClick={deleteSelectedDocuments}
          >
            {working === "delete_selected" ? "Deleting..." : "Delete"}
          </button>
          <button
            type="button"
            disabled={selected.length === 0 || !!working}
            onClick={() => setSelected([])}
          >
            Clear
          </button>
        </div>

        <div className={detail ? "content-grid detail-open" : "content-grid"}>
          <div className="document-list">
            {loading ? (
              <p className="empty-message">Loading...</p>
            ) : documents.length === 0 ? (
              <p className="empty-message">
                {query
                  ? "No matching documents."
                  : "No documents uploaded yet."}
              </p>
            ) : (
              documents.map((document) => {
                const isSelected = selected.includes(document.id);
                const selectionIndex = selected.indexOf(document.id);
                const isOpen = detail?.id === document.id;

                return (
                  <article
                    className={`document-row${isSelected ? " selected" : ""}`}
                    key={document.id}
                  >
                    <button
                      className="document-row-select"
                      type="button"
                      aria-label={`${isSelected ? "Deselect" : "Select"} ${document.name}`}
                      aria-pressed={isSelected}
                      onClick={() => toggleDocument(document.id)}
                    />
                    <input
                      aria-label={`Select ${document.name}`}
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleDocument(document.id)}
                    />
                    <div className="document-summary">
                      <strong>{document.name}</strong>
                      <span>
                        {formatFileType(
                          document.media_type,
                          document.original_filename,
                        )}{" "}
                        · {formatBytes(document.size_bytes)} ·{" "}
                        {formatDate(document.created_at)}
                      </span>
                    </div>
                    <div className="document-row-actions">
                      {selected.length <= 2 && selectionIndex >= 0 && (
                        <span className="selection-role">
                          {selectionIndex === 0 ? "Original" : "New version"}
                        </span>
                      )}
                      <StatusPill status={document.status} />
                      <button
                        className="view-button"
                        type="button"
                        aria-expanded={isOpen}
                        aria-controls="document-details"
                        disabled={working === "open"}
                        onClick={(event) => {
                          event.stopPropagation();
                          if (isOpen) {
                            setDetail(null);
                          } else {
                            openDocument(document.id);
                          }
                        }}
                      >
                        {isOpen ? "Close details" : "View details"}
                      </button>
                    </div>
                  </article>
                );
              })
            )}
          </div>

          {detail && (
            <aside className="document-detail" id="document-details">
              <div className="detail-title">
                <h2>{detail.name}</h2>
                <button
                  className="text-button"
                  type="button"
                  onClick={() => setDetail(null)}
                >
                  Close
                </button>
              </div>
              <dl>
                <div>
                  <dt>File</dt>
                  <dd>{detail.original_filename}</dd>
                </div>
                <div>
                  <dt>Pages</dt>
                  <dd>{detail.page_count ?? "N/A"}</dd>
                </div>
                <div>
                  <dt>Size</dt>
                  <dd>{formatBytes(detail.size_bytes)}</dd>
                </div>
              </dl>
              {detail.media_type === "application/pdf" &&
                detail.status === "ready" &&
                detail.page_count !== null && (
                  <div className="detail-actions">
                    <button
                      type="button"
                      disabled={!!working}
                      onClick={() => setPageToolsOpen(true)}
                    >
                      Page tools
                    </button>
                  </div>
                )}
              {detail.status === "failed" ? (
                <p className="detail-error">Text extraction failed.</p>
              ) : (
                <>
                  <h3>Extracted text</h3>
                  <pre className="extracted-text">
                    {detail.extracted_text ||
                      (detail.status === "ready"
                        ? "No text found."
                        : "Processing...")}
                  </pre>
                </>
              )}
            </aside>
          )}
        </div>
      </section>

      {comparison && (
        <ComparisonResult result={comparison} onClose={closeComparison} />
      )}

      {pageToolsOpen && detail && detail.page_count !== null && (
        <PageTools
          pageCount={detail.page_count}
          working={working}
          onClose={closePageTools}
          onExtract={(pages, name) => runPageTool("extract_pages", pages, name)}
          onSplit={() => runPageTool("split")}
        />
      )}

      <SiteFooter />
    </main>
  );
}
