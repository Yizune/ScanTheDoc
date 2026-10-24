"use client";

import { useRef, useState } from "react";
import { errorMessage, useApi } from "@/lib/api";

export function DocumentUpload({
  onUploaded,
  onError,
}: {
  onUploaded?: () => void | Promise<void>;
  onError?: (message: string) => void;
}) {
  const api = useApi();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);

  async function upload(file?: File) {
    if (!file) return;
    setUploading(true);
    const body = new FormData();
    body.append("file", file);
    try {
      await api("/api/v1/documents", { method: "POST", body });
      await onUploaded?.();
    } catch (error) {
      onError?.(errorMessage(error, "Upload failed. Try again."));
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <section className="upload-panel">
      <input
        ref={input}
        hidden
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp"
        onChange={(event) => upload(event.target.files?.[0])}
      />
      <button
        type="button"
        disabled={uploading}
        className={dragging ? "upload-zone dragging" : "upload-zone"}
        onClick={() => input.current?.click()}
        onDragEnter={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          upload(event.dataTransfer.files[0]);
        }}
      >
        <strong>
          {uploading ? "Uploading..." : "Drop a file here or choose a file"}
        </strong>
        <span>PDF, PNG, JPEG, TIFF or WebP · maximum 25 MB</span>
      </button>
    </section>
  );
}
