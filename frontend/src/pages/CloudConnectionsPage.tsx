import { useEffect, useState, type FormEvent } from "react";
import { cloudApi } from "../api/cloud";
import { getApiErrorMessage } from "../api/client";
import type { ConnectionStatus } from "../types";
import { Loading } from "../components/States";

type S3Form = {
  access_key_id: string;
  secret_access_key: string;
  region: string;
  endpoint_url: string;
  bucket_name: string;
};

const EMPTY_S3_FORM: S3Form = {
  access_key_id: "",
  secret_access_key: "",
  region: "",
  endpoint_url: "",
  bucket_name: "",
};

export function CloudConnectionsPage() {
  return (
    <div className="page">
      <header className="page-header">
        <h1>Cloud Connections</h1>
        <p className="page-subtitle">
          Connect Google Drive and S3-compatible storage (Backblaze B2 / AWS S3).
        </p>
      </header>
      <div className="dashboard-columns">
        <GoogleCard />
        <S3Card />
      </div>
    </div>
  );
}

function GoogleCard() {
  const [status, setStatus] = useState<ConnectionStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setStatus(await cloudApi.googleStatus());
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleConnect() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const { authorization_url } = await cloudApi.googleConnect();
      setNotice(
        "Google's consent page opened in a new tab. Complete the authorization, then refresh the status here."
      );
      window.open(authorization_url, "_blank", "noopener");
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDisconnect() {
    setBusy(true);
    setError(null);
    try {
      await cloudApi.googleDisconnect();
      await load();
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="google-card-title">
      <div className="card-header">
        <h2 id="google-card-title">Google Drive</h2>
        {loading ? null : (
          <span className={`connection-state ${status?.is_connected ? "on" : "off"}`}>
            {status?.is_connected ? "Connected" : "Disconnected"}
          </span>
        )}
      </div>
      {loading ? (
        <Loading label="Checking connection…" />
      ) : (
        <>
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          {notice && <div className="alert alert-info" role="status">{notice}</div>}
          <dl className="metadata-list">
            <div>
              <dt>Account</dt>
              <dd>{status?.account_identifier ?? "—"}</dd>
            </div>
            <div>
              <dt>Connected since</dt>
              <dd>{status?.connected_at ? new Date(status.connected_at).toLocaleString() : "—"}</dd>
            </div>
            {status?.detail && (
              <div>
                <dt>Info</dt>
                <dd>{status.detail}</dd>
              </div>
            )}
          </dl>
          <div className="card-actions">
            {status?.is_connected ? (
              <button type="button" className="btn btn-danger" onClick={handleDisconnect} disabled={busy}>
                {busy ? "Disconnecting…" : "Disconnect"}
              </button>
            ) : (
              <button type="button" className="btn btn-primary" onClick={handleConnect} disabled={busy}>
                {busy ? "Starting…" : "Connect Google Drive"}
              </button>
            )}
            <button type="button" className="btn btn-secondary" onClick={load} disabled={busy}>
              Refresh status
            </button>
          </div>
        </>
      )}
    </section>
  );
}

function S3Card() {
  const [status, setStatus] = useState<ConnectionStatus | null>(null);
  const [form, setForm] = useState<S3Form>(EMPTY_S3_FORM);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setStatus(await cloudApi.s3Status());
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleConnect(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      // Empty fields fall back to the server's S3_* environment configuration.
      const payload = Object.fromEntries(
        Object.entries(form).filter(([, value]) => value.trim() !== "")
      );
      const response = await cloudApi.s3Connect(payload);
      setNotice(response.message ?? `Connected to bucket ${response.bucket}.`);
      setForm(EMPTY_S3_FORM);
      await load();
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDisconnect() {
    setBusy(true);
    setError(null);
    try {
      await cloudApi.s3Disconnect();
      await load();
    } catch (err) {
      setError(getApiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="s3-card-title">
      <div className="card-header">
        <h2 id="s3-card-title">S3-compatible storage</h2>
        {loading ? null : (
          <span className={`connection-state ${status?.is_connected ? "on" : "off"}`}>
            {status?.is_connected ? "Connected" : "Disconnected"}
          </span>
        )}
      </div>
      {loading ? (
        <Loading label="Checking connection…" />
      ) : (
        <>
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          {notice && <div className="alert alert-info" role="status">{notice}</div>}
          <dl className="metadata-list">
            <div>
              <dt>Bucket</dt>
              <dd>{status?.account_identifier ?? "—"}</dd>
            </div>
            {status?.detail && (
              <div>
                <dt>Info</dt>
                <dd>{status.detail}</dd>
              </div>
            )}
          </dl>

          {status?.is_connected ? (
            <div className="card-actions">
              <button type="button" className="btn btn-danger" onClick={handleDisconnect} disabled={busy}>
                {busy ? "Disconnecting…" : "Disconnect"}
              </button>
              <button type="button" className="btn btn-secondary" onClick={load} disabled={busy}>
                Refresh status
              </button>
            </div>
          ) : (
            <form onSubmit={handleConnect} className="stacked-form">
              <p className="form-hint">
                Leave fields empty to use the server's configured S3 credentials.
              </p>
              <div className="form-field">
                <label className="form-label" htmlFor="s3-access-key">Access key ID</label>
                <input
                  id="s3-access-key"
                  className="form-input"
                  type="text"
                  autoComplete="off"
                  value={form.access_key_id}
                  onChange={(e) => setForm({ ...form, access_key_id: e.target.value })}
                />
              </div>
              <div className="form-field">
                <label className="form-label" htmlFor="s3-secret">Secret access key</label>
                <input
                  id="s3-secret"
                  className="form-input"
                  type="password"
                  autoComplete="new-password"
                  value={form.secret_access_key}
                  onChange={(e) => setForm({ ...form, secret_access_key: e.target.value })}
                />
              </div>
              <div className="form-row">
                <div className="form-field">
                  <label className="form-label" htmlFor="s3-bucket">Bucket name</label>
                  <input
                    id="s3-bucket"
                    className="form-input"
                    type="text"
                    value={form.bucket_name}
                    onChange={(e) => setForm({ ...form, bucket_name: e.target.value })}
                  />
                </div>
                <div className="form-field">
                  <label className="form-label" htmlFor="s3-region">Region</label>
                  <input
                    id="s3-region"
                    className="form-input"
                    type="text"
                    placeholder="us-west-004"
                    value={form.region}
                    onChange={(e) => setForm({ ...form, region: e.target.value })}
                  />
                </div>
              </div>
              <div className="form-field">
                <label className="form-label" htmlFor="s3-endpoint">Endpoint URL</label>
                <input
                  id="s3-endpoint"
                  className="form-input"
                  type="url"
                  placeholder="https://s3.us-west-004.backblazeb2.com"
                  value={form.endpoint_url}
                  onChange={(e) => setForm({ ...form, endpoint_url: e.target.value })}
                />
              </div>
              <div className="card-actions">
                <button type="submit" className="btn btn-primary" disabled={busy}>
                  {busy ? "Connecting…" : "Connect"}
                </button>
                <button type="button" className="btn btn-secondary" onClick={load} disabled={busy}>
                  Refresh status
                </button>
              </div>
            </form>
          )}
        </>
      )}
    </section>
  );
}
