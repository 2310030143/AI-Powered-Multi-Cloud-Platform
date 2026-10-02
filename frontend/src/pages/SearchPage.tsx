import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { searchApi } from "../api/search";
import { getApiErrorMessage } from "../api/client";
import type { CloudProvider, SearchResponse } from "../types";
import { EmptyState, ErrorState, Loading } from "../components/States";

export function SearchPage() {
  const [query, setQuery] = useState("");
  const [source, setSource] = useState<"" | CloudProvider>("");
  const [mimeType, setMimeType] = useState("");
  const [minScore, setMinScore] = useState("");
  const [limit, setLimit] = useState("10");
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!query.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const response = await searchApi.search({
        query: query.trim(),
        limit: Math.max(1, Math.min(50, Number(limit) || 10)),
        min_score: minScore ? Number(minScore) : undefined,
        source: source || undefined,
        mime_type: mimeType.trim() || undefined,
      });
      setResults(response);
      setSearched(true);
    } catch (err) {
      setError(getApiErrorMessage(err));
      setResults(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>Semantic Search</h1>
        <p className="page-subtitle">
          Search your indexed documents by meaning — powered by Jina embeddings and Qdrant.
        </p>
      </header>

      <form className="card search-form" onSubmit={handleSubmit}>
        <div className="search-bar">
          <input
            type="search"
            className="form-input filter-grow"
            placeholder="What are you looking for?"
            aria-label="Search query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            required
          />
          <button type="submit" className="btn btn-primary" disabled={loading || !query.trim()}>
            {loading ? "Searching…" : "Search"}
          </button>
        </div>
        <div className="filter-bar">
          <select
            className="form-input"
            aria-label="Filter by source"
            value={source}
            onChange={(e) => setSource(e.target.value as "" | CloudProvider)}
          >
            <option value="">All sources</option>
            <option value="google_drive">Google Drive</option>
            <option value="s3">S3</option>
          </select>
          <input
            className="form-input"
            type="text"
            placeholder="MIME type (e.g. application/pdf)"
            aria-label="Filter by MIME type"
            value={mimeType}
            onChange={(e) => setMimeType(e.target.value)}
          />
          <input
            className="form-input"
            type="number"
            min="0"
            max="1"
            step="0.05"
            placeholder="Min score"
            aria-label="Minimum similarity score"
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
          />
          <input
            className="form-input"
            type="number"
            min="1"
            max="50"
            aria-label="Result limit"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          />
        </div>
      </form>

      {loading && <Loading label="Searching your documents…" />}
      {error && <ErrorState message={error} />}

      {!loading && !error && results && results.results.length === 0 && (
        <EmptyState
          title="No matching content found"
          detail="Try a different query, lower the minimum score, or clear filters."
        />
      )}

      {!loading && !error && results && results.results.length > 0 && (
        <section aria-label="Search results">
          <p className="muted">
            {results.total} result{results.total === 1 ? "" : "s"} for “{results.query}”
          </p>
          <ul className="result-list">
            {results.results.map((hit) => (
              <li key={hit.chunk_id ?? `${hit.document_id}-${hit.chunk_index}`} className="card result-card">
                <div className="result-header">
                  {hit.document_id ? (
                    <Link to={`/documents/${hit.document_id}`} className="table-link">
                      {hit.file_name ?? "Document"}
                    </Link>
                  ) : (
                    <span>{hit.file_name ?? "Document"}</span>
                  )}
                  <span className="score-pill" title="Cosine similarity">
                    {hit.score.toFixed(3)}
                  </span>
                </div>
                <p className="result-content">{hit.content}</p>
                <div className="result-meta">
                  {hit.source && <span>{hit.source}</span>}
                  {hit.mime_type && <span>{hit.mime_type}</span>}
                  {hit.page_number != null && <span>page {hit.page_number}</span>}
                  {hit.token_count != null && <span>{hit.token_count} tokens</span>}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {!loading && !error && !searched && (
        <EmptyState
          title="Search across your documents"
          detail="Results are ranked by semantic similarity to your query."
        />
      )}
    </div>
  );
}
