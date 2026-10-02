import { Link } from "react-router-dom";
import type { FeatureSource } from "../types";

/**
 * Application-side source attribution display (Phase 5/6 conventions).
 * Sources come from the backend — never fabricated by the UI.
 */
export function SourceList({ sources }: { sources: FeatureSource[] }) {
  if (sources.length === 0) return null;
  return (
    <div className="sources">
      <h4 className="sources-title">Sources ({sources.length})</h4>
      <ul className="source-list">
        {sources.map((source) => (
          <li key={source.chunk_id} className="source-item">
            {source.document_id ? (
              <Link to={`/documents/${source.document_id}`} className="source-link">
                {source.filename ?? source.document_id}
              </Link>
            ) : (
              <span>{source.filename ?? "Unknown file"}</span>
            )}
            {source.page_number != null && <span className="source-meta">page {source.page_number}</span>}
            {source.score != null && (
              <span className="source-meta">score {source.score.toFixed(3)}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
