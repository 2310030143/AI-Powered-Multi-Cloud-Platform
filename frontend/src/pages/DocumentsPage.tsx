import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { documentsApi } from "../api/documents";
import { filesApi } from "../api/files";
import { getApiErrorMessage } from "../api/client";
import type { CloudFile, CloudProvider, Document, ProcessingStatus } from "../types";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";

const PAGE_SIZE = 20;

type ProviderFilter = "" | CloudProvider;
type StatusFilter = "" | ProcessingStatus;

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(1)} ${units[unit]}`;
}

export function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [providerFilter, setProviderFilter] = useState<ProviderFilter>("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("");
  const [nameFilter, setNameFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await documentsApi.list({
        provider: providerFilter || undefined,
        processingStatus: statusFilter || undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setDocuments(response.items);
      setTotal(response.total);
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [providerFilter, statusFilter, offset]);

  useEffect(() => {
    load();
  }, [load, reloadKey]);

  // Client-side name filtering over the loaded page (the documents API does
  // not support name search; this is a safe local refinement).
  const visible = nameFilter.trim()
    ? documents.filter((doc) =>
        doc.file_name.toLowerCase().includes(nameFilter.trim().toLowerCase())
      )
    : documents;

  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + PAGE_SIZE, total);

  return (
    <div className="page">
      <header className="page-header">
        <h1>Documents</h1>
        <p className="page-subtitle">Browse, upload and import your files.</p>
      </header>

      <UploadImportPanel onDone={() => setReloadKey((k) => k + 1)} />

      <section className="card">
        <div className="card-header">
          <h2>Your documents</h2>
          <span className="muted">{total} total</span>
        </div>

        <div className="filter-bar">
          <input
            type="search"
            className="form-input filter-grow"
            placeholder="Filter by name (this page)…"
            aria-label="Filter documents by name"
            value={nameFilter}
            onChange={(e) => setNameFilter(e.target.value)}
          />
          <select
            className="form-input"
            aria-label="Filter by provider"
            value={providerFilter}
            onChange={(e) => {
              setOffset(0);
              setProviderFilter(e.target.value as ProviderFilter);
            }}
          >
            <option value="">All sources</option>
            <option value="google_drive">Google Drive</option>
            <option value="s3">S3</option>
          </select>
          <select
            className="form-input"
            aria-label="Filter by processing status"
            value={statusFilter}
            onChange={(e) => {
              setOffset(0);
              setStatusFilter(e.target.value as StatusFilter);
            }}
          >
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="processing">Processing</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
        </div>

        {loading ? (
          <Loading label="Loading documents…" />
        ) : error ? (
          <ErrorState message={error} onRetry={load} />
        ) : visible.length === 0 ? (
          <EmptyState
            title={documents.length === 0 ? "No documents yet" : "No documents match this filter"}
            detail="Upload a file above or import one from a connected cloud."
          />
        ) : (
          <>
            <div className="table-scroll">
              <table className="table">
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Type</th>
                    <th>Source</th>
                    <th>Size</th>
                    <th>Status</th>
                    <th>Added</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((doc) => (
                    <tr key={doc.id}>
                      <td>
                        <Link to={`/documents/${doc.id}`} className="table-link">{doc.file_name}</Link>
                      </td>
                      <td>{doc.mime_type ?? doc.file_type}</td>
                      <td>{doc.provider}</td>
                      <td>{formatBytes(doc.file_size)}</td>
                      <td><StatusBadge status={doc.processing_status} /></td>
                      <td>{new Date(doc.created_at).toLocaleDateString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination" aria-label="Pagination">
              <span className="muted">
                {nameFilter ? `${visible.length} shown` : `${pageStart}–${pageEnd} of ${total}`}
              </span>
              <div className="pagination-controls">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  Previous
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

// ─── Upload / Import panel ───────────────────────────────────────────────────

function UploadImportPanel({ onDone }: { onDone: () => void }) {
  const [tab, setTab] = useState<"upload" | "import">("upload");

  return (
    <section className="card" aria-labelledby="upload-import-title">
      <div className="card-header">
        <h2 id="upload-import-title">Add documents</h2>
        <div className="tab-group" role="tablist" aria-label="Add documents method">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "upload"}
            className={`tab ${tab === "upload" ? "active" : ""}`}
            onClick={() => setTab("upload")}
          >
            Upload file
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "import"}
            className={`tab ${tab === "import" ? "active" : ""}`}
            onClick={() => setTab("import")}
          >
            Import from cloud
          </button>
        </div>
      </div>
      {tab === "upload" ? <UploadForm onDone={onDone} /> : <CloudImportPanel onDone={onDone} />}
    </section>
  );
}

function UploadForm({ onDone }: { onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [provider, setProvider] = useState<CloudProvider>("s3");
  const [folderId, setFolderId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const doc = await filesApi.upload({ file, provider, folderId: folderId || undefined });
      setSuccess(`Uploaded "${doc.file_name}" — it is now tracked and ready to process.`);
      setFile(null);
      setFolderId("");
      onDone();
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stacked-form" onSubmit={handleSubmit}>
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {success && <div className="alert alert-success" role="status">{success}</div>}
      <div className="form-row">
        <div className="form-field">
          <label className="form-label" htmlFor="upload-provider">Upload to</label>
          <select
            id="upload-provider"
            className="form-input"
            value={provider}
            onChange={(e) => setProvider(e.target.value as CloudProvider)}
          >
            <option value="s3">S3-compatible storage</option>
            <option value="google_drive">Google Drive</option>
          </select>
        </div>
        <div className="form-field">
          <label className="form-label" htmlFor="upload-folder">Folder / prefix (optional)</label>
          <input
            id="upload-folder"
            className="form-input"
            type="text"
            placeholder="e.g. reports/"
            value={folderId}
            onChange={(e) => setFolderId(e.target.value)}
          />
        </div>
      </div>
      <div className="form-field">
        <label className="form-label" htmlFor="upload-file">File</label>
        <input
          id="upload-file"
          className="form-input"
          type="file"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          required
        />
        {file && <p className="form-hint">{file.name} ({formatBytes(file.size)})</p>}
      </div>
      <div className="card-actions">
        <button type="submit" className="btn btn-primary" disabled={!file || busy}>
          {busy ? "Uploading…" : "Upload"}
        </button>
      </div>
    </form>
  );
}

function CloudImportPanel({ onDone }: { onDone: () => void }) {
  const [provider, setProvider] = useState<CloudProvider>("s3");
  const [folderId, setFolderId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [files, setFiles] = useState<CloudFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const items = await filesApi.list({
        provider,
        folderId: folderId ?? undefined,
        search: search.trim() || undefined,
      });
      setFiles(items);
    } catch (err) {
      setFiles([]);
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [provider, folderId, search]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleImport(file: CloudFile) {
    setBusyId(file.file_id);
    setError(null);
    setNotice(null);
    try {
      const doc = await filesApi.import(file.file_id, provider);
      setNotice(`Imported "${doc.file_name}". Process it from the document list.`);
      onDone();
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  const folders = files.filter((f) => f.is_folder);
  const regularFiles = files.filter((f) => !f.is_folder);

  return (
    <div className="stacked-form">
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {notice && <div className="alert alert-success" role="status">{notice}</div>}
      <div className="filter-bar">
        <select
          className="form-input"
          aria-label="Cloud provider"
          value={provider}
          onChange={(e) => {
            setFolderId(null);
            setSearch("");
            setProvider(e.target.value as CloudProvider);
          }}
        >
          <option value="s3">S3-compatible storage</option>
          <option value="google_drive">Google Drive</option>
        </select>
        <input
          type="search"
          className="form-input filter-grow"
          placeholder="Search file names…"
          aria-label="Search cloud files"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button type="button" className="btn btn-secondary" onClick={load} disabled={loading}>
          Refresh
        </button>
      </div>

      {folderId && (
        <button type="button" className="btn btn-ghost" onClick={() => setFolderId(null)}>
          ← Back to root
        </button>
      )}

      {loading ? (
        <Loading label="Listing cloud files…" />
      ) : (
        <ul className="cloud-file-list">
          {folders.map((folder) => (
            <li key={folder.file_id} className="cloud-file folder">
              <button
                type="button"
                className="cloud-file-button"
                onClick={() => setFolderId(folder.file_id)}
              >
                <span className="cloud-file-icon" aria-hidden="true">📁</span>
                <span>{folder.name}</span>
              </button>
            </li>
          ))}
          {regularFiles.map((file) => (
            <li key={file.file_id} className="cloud-file">
              <span className="cloud-file-name" title={file.file_id}>
                <span className="cloud-file-icon" aria-hidden="true">📄</span> {file.name}
              </span>
              <span className="muted">{formatBytes(file.size)}</span>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => handleImport(file)}
                disabled={busyId === file.file_id}
              >
                {busyId === file.file_id ? "Importing…" : "Import"}
              </button>
            </li>
          ))}
          {files.length === 0 && (
            <li className="muted cloud-file-empty">
              No files found{folderId ? " in this folder" : ""}. Connect the cloud and try again.
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
