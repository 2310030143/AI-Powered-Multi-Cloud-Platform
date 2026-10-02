import { useState, type FormEvent } from "react";
import { reportsApi } from "../api/reports";
import { getApiErrorMessage } from "../api/client";
import type { ReportResponse } from "../types";
import { DocumentPicker, MAX_DOCUMENTS_PER_REQUEST } from "../components/DocumentPicker";
import { ErrorState } from "../components/States";
import { SourceList } from "../components/SourceList";

const REPORT_SECTIONS: { key: keyof ReportResponse["report"]; title: string }[] = [
  { key: "executive_summary", title: "Executive Summary" },
  { key: "key_findings", title: "Key Findings" },
  { key: "evidence", title: "Evidence" },
  { key: "recommendations", title: "Recommendations" },
  { key: "conclusion", title: "Conclusion" },
];

export function ReportsPage() {
  const [selected, setSelected] = useState<string[]>([]);
  const [instruction, setInstruction] = useState("");
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (loading || selected.length === 0 || !instruction.trim()) return;
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      setReport(await reportsApi.generate({ document_ids: selected, instruction: instruction.trim() }));
    } catch (err) {
      setError(getApiErrorMessage(err, "Unable to generate the report."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>Report Generation</h1>
        <p className="page-subtitle">
          Generate a structured report from up to {MAX_DOCUMENTS_PER_REQUEST} of your documents.
        </p>
      </header>

      <form className="card stacked-form" onSubmit={handleSubmit}>
        {error && <ErrorState message={error} />}
        <DocumentPicker selected={selected} onChange={setSelected} />
        <div className="form-field">
          <label className="form-label" htmlFor="report-instruction">Report instruction</label>
          <textarea
            id="report-instruction"
            className="form-input form-textarea"
            placeholder="e.g. Summarize the key security recommendations across these documents."
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            maxLength={2000}
            rows={3}
            required
          />
        </div>
        <div className="card-actions">
          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading || selected.length === 0 || !instruction.trim()}
          >
            {loading ? "Generating…" : "Generate report"}
          </button>
        </div>
      </form>

      {loading && <p className="muted" role="status">Generating your report…</p>}

      {report && (
        <section className="card report-card" aria-labelledby="report-result-title">
          <div className="card-header">
            <h2 id="report-result-title">Report</h2>
            {report.provider && <span className="badge">{report.provider}</span>}
          </div>
          {REPORT_SECTIONS.map(({ key, title }) => (
            <div key={key} className="report-section">
              <h3 className="report-section-title">{title}</h3>
              <p className="ai-output">{report.report[key]}</p>
            </div>
          ))}
          <SourceList sources={report.sources} />
        </section>
      )}
    </div>
  );
}
