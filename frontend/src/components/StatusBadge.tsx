const LABELS: Record<string, string> = {
  pending: "Pending",
  processing: "Processing",
  completed: "Completed",
  failed: "Failed",
};

export function StatusBadge({ status }: { status: string | null | undefined }) {
  const key = status ?? "unknown";
  return <span className={`badge status-${key}`}>{LABELS[key] ?? key}</span>;
}
