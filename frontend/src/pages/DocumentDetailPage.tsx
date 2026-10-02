import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { documentsApi } from "../api/documents";
import { filesApi } from "../api/files";
import { getApiErrorMessage } from "../api/client";
import type { Document as DocumentModel, DocumentStatus, ChunkListResponse, TableListResponse, SummarizeResponse } from "../types";
import { ErrorState, Loading } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import { SourceList } from "../components/SourceList";
import { formatBytes } from "./DocumentsPage";

const POLL_INTERVAL_MS = 3000;
const MAX_POLLS = 100; // hard cap — never poll indefinitely

export function DocumentDetailPage() {
  const { documentId } = useParams<{ documentId: string }>();

  const [doc, setDoc] = useState<DocumentModel | null>(null);
  const [status, setStatus] = useState<DocumentStatus | null>(null);
  const [chunks, setChunks] = useState<ChunkListResponse | null>(null);
  const [tables, setTables] = useState<TableListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [summary, setSummary] = useState<SummarizeResponse | null>(null);
  const [downloading, setDownloading] = useState(false);
  const pollCount = useRef(0);

  const load = useCallback(async () => {
    if (!documentId) return;
    setLoading(true);
    setError(null);
    try {
      const [doc, docStatus, docChunks, docTables] = await Promise.all([
        documentsApi.get(documentId),
        documentsApi.status(documentId),
        documentsApi.chunks(documentId, 20),
        documentsApi.tables(documentId),
      ]);
      setDoc(doc);
      setStatus(docStatus);
      setChunks(docChunks);
      setTables(docTables);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    load();
  }, [load]);

  // Poll while the document is processing; stop on completion/failure or cap.
  useEffect(() => {
    if (status?.processing_status !== "processing") {
      pollCount.current = 0;
      return;
    }
    if (pollCount.current >= MAX_POLLS) return;
    const timer = setInterval(async () => {
      pollCount.current += 1;
      try {
        const next = await documentsApi.status(documentId!);
        setStatus(next);
        if (next.processing_status !== "processing") {
          setNotice(
            next.processing_status === "completed"
              ? "Processing completed."
              : "Processing finished with an error — see the jobs below."
          );
          const [doc, docChunks, docTables] = await Promise.all([
            documentsApi.get(documentId!),
            documentsApi.chunks(documentId!, 20),
            documentsApi.tables(documentId!),
          ]);
          setDoc(doc);
          setChunks(docChunks);
          setTables(docTables);
        }
      } catch {
        // transient polling errors are ignored; the next tick retries
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [status?.processing_status, documentId]);

  async function handleProcess() {
    if (!documentId || processing) return;
    setProcessing(true);
    setActionError(null);
    setNotice(null);
    try {
      await documentsApi.process(documentId);
      setNotice("Processing started…");
      pollCount.current = 0;
      const next = await documentsApi.status(documentId);
      setStatus(next);
    } catch (err) {
      setActionError(getApiErrorMessage(err));
    } finally {
      setProcessing(false);
    }
  }

  async function handleSummarize() {
    if (!documentId || summarizing) return;
    setSummarizing(true);
    setActionError(null);
    setSummary(null);
    try {
      setSummary(await documentsApi.summarize(documentId));
    } catch (err) {
      setActionError(getApiErrorMessage(err, "Unable to summarize this document."));
    } finally {
      setSummarizing(false);
    }
  }

  async function handleDownload() {
    if (!doc || downloading) return;
    setDownloading(true);
    setActionError(null);
    try {
      const blob = await filesApi.download(doc.external_file_id, doc.provider as "s3" | "google_drive");
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = doc.file_name;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setActionError(getApiErrorMessage(err, "Unable to download this file."));
    } finally {
      setDownloading(false);
    }
  }

  if (loading) return <Loading label="Loading document…" />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!doc) return null;

  return (
    <div className="page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/documents">Documents</Link> <span aria-hidden="true">/</span>{" "}
        <span>{doc.file_name}</span>
      </nav>

      <header className="page-header">
        <h1>{doc.file_name}</h1>
        <div className="header-badges">
          <StatusBadge status={doc.processing_status} />
          <span className="badge">{doc.provider}</span>
          {doc.embedding_completed && <span className="badge badge-ok">Embedded</span>}
          {doc.ocr_required && <span className="badge">OCR</span>}
        </div>
      </header>

      {actionError && <div className="alert alert-error" role="alert">{actionError}</div>}
      {notice && <div className="alert alert-info" role="status">{notice}</div>}

      <div className="detail-grid">
        <section className="card" aria-labelledby="metadata-title">
          <div className="card-header">
            <h2 id="metadata-title">Metadata</h2>
          </div>
          <dl className="metadata-list">
            <div><dt>Document ID</dt><dd className="mono">{doc.id}</dd></div>
            <div><dt>File type</dt><dd>{doc.mime_type ?? doc.file_type}</dd></div>
            <div><dt>Size</dt><dd>{formatBytes(doc.file_size)}</dd></div>
            <div><dt>Source</dt><dd>{doc.provider}</dd></div>
            <div><dt>Created</dt><dd>{new Date(doc.created_at).toLocaleString()}</dd></div>
            <div><dt>Updated</dt><dd>{new Date(doc.modified_at).toLocaleString()}</dd></div>
            <div><dt>Chunks</dt><dd>{chunks?.total ?? "—"}</dd></div>
            <div><dt>Tables extracted</dt><dd>{tables?.total ?? "—"}</dd></div>
            {doc.content_hash && (
              <div><dt>Content hash</dt><dd className="mono">{doc.content_hash.slice(0, 16)}…</dd></div>
            )}
          </dl>
          <div className="card-actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleProcess}
              disabled={processing || doc.processing_status === "processing"}
            >
              {processing || doc.processing_status === "processing"
                ? "Processing…"
                : doc.processing_status === "completed"
                  ? "Reprocess"
                  : "Process document"}
            </button>
            <button type="button" className="btn btn-secondary" onClick={handleSummarize} disabled={summarizing}>
              {summarizing ? "Summarizing…" : "Summarize document"}
            </button>
            <button type="button" className="btn btn-secondary" onClick={handleDownload} disabled={downloading}>
              {downloading ? "Downloading…" : "Download"}
            </button>
          </div>
        </section>

        <section className="card" aria-labelledby="processing-title">
          <div className="card-header">
            <h2 id="processing-title">Processing status</h2>
            {status && <StatusBadge status={status.processing_status} />}
          </div>
          {status && status.jobs.length > 0 ? (
            <ul className="job-list">
              {status.jobs.map((job, index) => (
                <li key={index} className="job-row">
                  <span className="job-type">{job.job_type}</span>
                  <StatusBadge status={job.status} />
                  {job.error_message && <span className="job-error">{job.error_message}</span>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No processing jobs yet — run "Process document".</p>
          )}
        </section>
      </div>

      {summary && (
        <section className="card" aria-labelledby="summary-title">
          <div className="card-header">
            <h2 id="summary-title">AI summary</h2>
            {summary.provider && <span className="badge">{summary.provider}</span>}
          </div>
          <p className="ai-output">{summary.summary}</p>
          <SourceList sources={summary.sources} />
        </section>
      )}

      <section className="card" aria-labelledby="chunks-title">
        <div className="card-header">
          <h2 id="chunks-title">Chunks</h2>
          {chunks && <span className="muted">{chunks.total} total</span>}
        </div>
        {chunks && chunks.items.length > 0 ? (
          <ul className="chunk-list">
            {chunks.items.map((chunk) => (
              <li key={chunk.id} className="chunk-item">
                <div className="chunk-meta">
                  <span>#{chunk.chunk_index}</span>
                  {chunk.page_number != null && <span>page {chunk.page_number}</span>}
                  {chunk.token_count != null && <span>{chunk.token_count} tokens</span>}
                </div>
                <p className="chunk-content">{chunk.content}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No chunks — process the document first.</p>
        )}
      </section>

      <section className="card" aria-labelledby="tables-title">
        <div className="card-header">
          <h2 id="tables-title">Extracted tables</h2>
          {tables && <span className="muted">{tables.total} total</span>}
        </div>
        {tables && tables.items.length > 0 ? (
          tables.items.map((table) => (
            <div key={table.id} className="table-block">
              <p className="table-caption">
                Table {table.table_index}
                {table.page_number != null && ` · page ${table.page_number}`}
                {table.row_count != null && ` · ${table.row_count}×${table.col_count}`}
              </p>
              <div className="table-scroll">
                <table className="table data-table">
                  <tbody>
                    {table.table_data.map((row, rowIndex) => (
                      <tr key={rowIndex}>
                        {row.map((cell, cellIndex) => (
                          <td key={cellIndex}>{cell}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))
        ) : (
          <p className="muted">No tables extracted for this document.</p>
        )}
      </section>
    </div>
  );
}
