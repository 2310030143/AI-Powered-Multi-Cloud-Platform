import { useEffect, useRef, useState, type FormEvent } from "react";
import { chatApi } from "../api/chat";
import { getApiErrorMessage } from "../api/client";
import type { ChatSource } from "../types";
import { EmptyState } from "../components/States";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources: ChatSource[];
}

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  async function handleSend(event: FormEvent) {
    event.preventDefault();
    const message = input.trim();
    if (!message || sending) return;
    setSending(true);
    setError(null);
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: message, sources: [] }]);
    try {
      const response = await chatApi.send({ message });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: response.answer, sources: response.sources },
      ]);
    } catch (err) {
      setError(getApiErrorMessage(err, "The assistant is unavailable right now."));
      // keep the user message visible so they can retry
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="page chat-page">
      <header className="page-header">
        <h1>AI Chat</h1>
        <p className="page-subtitle">
          Ask questions about your documents — answers are generated from your indexed content.
        </p>
      </header>

      <div className="chat-container card">
        {messages.length === 0 && !sending && (
          <EmptyState
            title="Ask anything about your documents"
            detail="The assistant answers using only your indexed document content and shows the sources it used. Documents must be processed (and embedded) to be searchable."
          />
        )}

        <ul className="chat-messages" aria-live="polite">
          {messages.map((message, index) => (
            <li key={index} className={`chat-message ${message.role}`}>
              <div className="chat-bubble">
                <p className="chat-text">{message.content}</p>
                {message.role === "assistant" && message.sources.length > 0 && (
                  <div className="sources">
                    <h4 className="sources-title">Sources ({message.sources.length})</h4>
                    <ul className="source-list">
                      {message.sources.map((source) => (
                        <li key={source.chunk_id} className="source-item">
                          <span>{source.filename ?? "Document"}</span>
                          {source.page_number != null && (
                            <span className="source-meta">page {source.page_number}</span>
                          )}
                          <span className="source-meta">score {source.score.toFixed(3)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </li>
          ))}
          {sending && (
            <li className="chat-message assistant">
              <div className="chat-bubble chat-thinking">
                <span className="spinner" aria-hidden="true" />
                <span>Searching your documents and thinking…</span>
              </div>
            </li>
          )}
          <div ref={bottomRef} />
        </ul>

        {error && <div className="alert alert-error" role="alert">{error}</div>}

        <form className="chat-input-row" onSubmit={handleSend}>
          <input
            type="text"
            className="form-input filter-grow"
            placeholder="Ask a question about your documents…"
            aria-label="Chat message"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            maxLength={2000}
          />
          <button type="submit" className="btn btn-primary" disabled={sending || !input.trim()}>
            {sending ? "Sending…" : "Send"}
          </button>
        </form>
      </div>
    </div>
  );
}
