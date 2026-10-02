import { useEffect, useState } from "react";
import { documentsApi } from "../api/documents";
import type { Document } from "../types";
import { EmptyState, ErrorState, Loading } from "./States";
import { getApiErrorMessage } from "../api/client";

// Backend-enforced limit (AI_MAX_DOCUMENTS, Phase 6). The backend validates
// this too — the frontend just mirrors the documented configuration.
export const MAX_DOCUMENTS_PER_REQUEST = 10;

/**
 * Shared multi-document selector for report generation and analysis.
 * Loads the user's documents from the real API and enforces the backend cap.
 */
export function DocumentPicker({
  selected,
  onChange,
  max = MAX_DOCUMENTS_PER_REQUEST,
}: {
  selected: string[];
  onChange: (ids: string[]) => void;
  max?: number;
}) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const response = await documentsApi.list({ limit: 100 });
      setDocuments(response.items);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function toggle(id: string) {
    if (selected.includes(id)) {
      onChange(selected.filter((x) => x !== id));
    } else if (selected.length < max) {
      onChange([...selected, id]);
    }
  }

  if (loading) return <Loading label="Loading your documents…" />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (documents.length === 0) {
    return (
      <EmptyState
        title="No documents yet"
        detail="Upload or import documents first — they need to be processed before analysis."
      />
    );
  }

  return (
    <div className="document-picker">
      <div className="picker-header">
        <label className="form-label" htmlFor="document-picker-list">
          Select documents ({selected.length}/{max})
        </label>
        {selected.length > 0 && (
          <button type="button" className="btn btn-ghost" onClick={() => onChange([])}>
            Clear
          </button>
        )}
      </div>
      <ul id="document-picker-list" className="picker-list" role="group" aria-label="Document selection">
        {documents.map((doc) => (
          <li key={doc.id}>
            <label className={`picker-item ${selected.includes(doc.id) ? "selected" : ""}`}>
              <input
                type="checkbox"
                checked={selected.includes(doc.id)}
                onChange={() => toggle(doc.id)}
                disabled={!selected.includes(doc.id) && selected.length >= max}
              />
              <span className="picker-name">{doc.file_name}</span>
              <span className="picker-meta">{doc.provider}</span>
              <span className="picker-meta">{doc.processing_status}</span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}
