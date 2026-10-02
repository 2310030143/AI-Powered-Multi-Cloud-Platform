import { useState, type FormEvent } from "react";
import { analysisApi } from "../api/analysis";
import { getApiErrorMessage } from "../api/client";
import type { AnalysisResponse } from "../types";
import { DocumentPicker, MAX_DOCUMENTS_PER_REQUEST } from "../components/DocumentPicker";
import { ErrorState } from "../components/States";
import { SourceList } from "../components/SourceList";

export function AnalysisPage() {
  const [selected, setSelected] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (loading || selected.length === 0 || !question.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await analysisApi.analyze({ document_ids: selected, question: question.trim() }));
    } catch (err) {
      setError(getApiErrorMessage(err, "Unable to run the analysis."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>Multi-Document Analysis</h1>
        <p className="page-subtitle">
          Compare and synthesize across up to {MAX_DOCUMENTS_PER_REQUEST} of your documents.
        </p>
      </header>

      <form className="card stacked-form" onSubmit={handleSubmit}>
        {error && <ErrorState message={error} />}
        <DocumentPicker selected={selected} onChange={setSelected} />
        <div className="form-field">
          <label className="form-label" htmlFor="analysis-question">Analysis question</label>
          <textarea
            id="analysis-question"
            className="form-input form-textarea"
            placeholder="e.g. How do these documents differ in their recommendations?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={2000}
            rows={3}
            required
          />
        </div>
        <div className="card-actions">
          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading || selected.length === 0 || !question.trim()}
          >
            {loading ? "Analyzing…" : "Run analysis"}
          </button>
        </div>
      </form>

      {loading && <p className="muted" role="status">Analyzing your documents…</p>}

      {result && (
        <section className="card" aria-labelledby="analysis-result-title">
          <div className="card-header">
            <h2 id="analysis-result-title">Analysis result</h2>
            {result.provider && <span className="badge">{result.provider}</span>}
          </div>
          <p className="ai-output">{result.analysis}</p>
          <SourceList sources={result.sources} />
        </section>
      )}
    </div>
  );
}
