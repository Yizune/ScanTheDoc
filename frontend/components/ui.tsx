export function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

const FILE_TYPE_LABELS: Record<string, string> = {
  "application/pdf": "PDF",
  "image/jpeg": "JPEG",
  "image/png": "PNG",
  "image/tiff": "TIFF",
  "image/webp": "WebP",
};

export function formatFileType(mediaType: string, filename: string): string {
  const knownType = FILE_TYPE_LABELS[mediaType];
  if (knownType) return knownType;

  const extension = filename.split(".").pop();
  return extension && extension !== filename ? extension.toUpperCase() : "File";
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-SE", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function StatusPill({ status }: { status: string }) {
  const visibleStatus = status === "queued" ? "processing" : status;

  return (
    <span className={`status-pill status-${visibleStatus}`}>
      {visibleStatus}
    </span>
  );
}
