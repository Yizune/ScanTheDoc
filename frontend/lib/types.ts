export type DocumentStatus = "queued" | "processing" | "ready" | "failed";

export interface DocumentItem {
  id: string;
  name: string;
  original_filename: string;
  media_type: string;
  size_bytes: number;
  status: DocumentStatus;
  page_count: number | null;
  extracted_text?: string;
  created_at: string;
}

export interface ProcessingJob {
  id: string;
  status: "queued" | "processing" | "completed" | "failed";
  result_document_id: string | null;
  result_data: {
    similarity_percent?: number;
    changes?: PdfComparisonChange[];
    changes_truncated?: boolean;
    original_pages?: PdfPageInfo[];
    compared_pages?: PdfPageInfo[];
  } | null;
  error_message: string | null;
}

export interface PdfPageInfo {
  page: number;
  width: number;
  height: number;
}

export interface PdfHighlight {
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PdfComparisonChange {
  id: string;
  kind: "added" | "removed" | "replaced";
  original_text: string;
  compared_text: string;
  original_highlights: PdfHighlight[];
  compared_highlights: PdfHighlight[];
}
