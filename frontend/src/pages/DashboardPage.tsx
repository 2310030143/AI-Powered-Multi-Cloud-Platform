import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { cloudApi } from "../api/cloud";
import { documentsApi } from "../api/documents";
import { getApiErrorMessage } from "../api/client";
import type { ConnectionStatus, Document } from "../types";
import { EmptyState, ErrorState, Loading } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";

interface DashboardData {
  documentsTotal: number;
  processingCount: number;
  pendingCount: number;
  recent: Document[];
  google: ConnectionStatus;
  s3: ConnectionStatus;
}

/**
 * All metrics come from real backend responses (documents + cloud status).
 * Nothing is fabricated: counts are derived from the documents API totals.
 */
export function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [all, processing, pending, recent, google, s3] = await Promise.all([
        documentsApi.list({ limit: 1 }),
        documentsApi.list({ processingStatus: "processing", limit: 1 }),
        documentsApi.list({ processingStatus: "pending", limit: 1 }),
        documentsApi.list({ limit: 5 }),
        cloudApi.googleStatus(),
        cloudApi.s3Status(),
      ]);
      setData({
        documentsTotal: all.total,
        processingCount: processing.total,
        pendingCount: pending.total,
        recent: recent.items,
        google,
        s3,
      });
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  if (loading) return <Loading label="Loading dashboard…" />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return null;

  return (
    <div className="page">
      <header className="page-header">
        <h1>Dashboard</h1>
        <p className="page-subtitle">Overview of your documents and cloud connections.</p>
      </header>

      <section className="stat-grid" aria-label="Key metrics">
        <div className="stat-card">
          <span className="stat-value">{data.documentsTotal}</span>
          <span className="stat-label">Documents</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{data.processingCount}</span>
          <span className="stat-label">Processing now</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{data.pendingCount}</span>
          <span className="stat-label">Pending</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">
            {Number(data.google.is_connected) + Number(data.s3.is_connected)}
          </span>
          <span className="stat-label">Clouds connected</span>
        </div>
      </section>

      <section className="dashboard-columns">
        <div className="card">
          <div className="card-header">
            <h2>Cloud connections</h2>
            <Link className="card-link" to="/cloud">Manage →</Link>
          </div>
          <ul className="connection-list">
            <li className="connection-row">
              <span>Google Drive</span>
              <span className={`connection-state ${data.google.is_connected ? "on" : "off"}`}>
                {data.google.is_connected
                  ? `Connected (${data.google.account_identifier ?? "account"})`
                  : "Not connected"}
              </span>
            </li>
            <li className="connection-row">
              <span>S3-compatible storage</span>
              <span className={`connection-state ${data.s3.is_connected ? "on" : "off"}`}>
                {data.s3.is_connected
                  ? `Connected (${data.s3.account_identifier ?? "bucket"})`
                  : "Not connected"}
              </span>
            </li>
          </ul>
        </div>

        <div className="card">
          <div className="card-header">
            <h2>Quick actions</h2>
          </div>
          <div className="quick-actions">
            <Link to="/documents" className="quick-action">Upload / import files</Link>
            <Link to="/search" className="quick-action">Semantic search</Link>
            <Link to="/chat" className="quick-action">Ask the AI assistant</Link>
            <Link to="/reports" className="quick-action">Generate a report</Link>
            <Link to="/analysis" className="quick-action">Analyze documents</Link>
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card-header">
          <h2>Recently added documents</h2>
          <Link className="card-link" to="/documents">All documents →</Link>
        </div>
        {data.recent.length === 0 ? (
          <EmptyState
            title="No documents yet"
            detail="Upload a file or import one from a connected cloud to get started."
          />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>File</th>
                <th>Source</th>
                <th>Status</th>
                <th>Added</th>
              </tr>
            </thead>
            <tbody>
              {data.recent.map((doc) => (
                <tr key={doc.id}>
                  <td>
                    <Link to={`/documents/${doc.id}`} className="table-link">{doc.file_name}</Link>
                  </td>
                  <td>{doc.provider}</td>
                  <td><StatusBadge status={doc.processing_status} /></td>
                  <td>{new Date(doc.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
