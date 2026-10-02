import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { DocumentDetailPage } from "../pages/DocumentDetailPage";
import { AuthProvider } from "../context/AuthContext";

const summarizeMock = vi.fn();

vi.mock("../api/documents", () => ({
  documentsApi: {
    get: vi.fn().mockResolvedValue({
      id: "d1", provider: "s3", external_file_id: "files/report.pdf", file_name: "report.pdf",
      file_type: "pdf", file_size: 4096, mime_type: "application/pdf", source_path: null,
      content_hash: "abc123", processing_status: "completed", ocr_required: false,
      ocr_completed: false, embedding_completed: true,
      created_at: "2026-01-01T10:00:00", modified_at: "2026-01-01T10:00:00",
    }),
    status: vi.fn().mockResolvedValue({
      document_id: "d1", file_name: "report.pdf", processing_status: "completed",
      ocr_required: false, ocr_completed: false, embedding_completed: true, jobs: [],
    }),
    chunks: vi.fn().mockResolvedValue({
      total: 1,
      items: [{ id: "c1", chunk_index: 0, page_number: 1, content: "chunk text here", token_count: 10, created_at: "2026-01-01" }],
    }),
    tables: vi.fn().mockResolvedValue({ total: 0, items: [] }),
    summarize: (...args: unknown[]) => summarizeMock(...args),
  },
}));

vi.mock("../api/files", () => ({ filesApi: { download: vi.fn() } }));

function renderPage() {
  return render(
    <AuthProvider>
      <MemoryRouter initialEntries={["/documents/d1"]}>
        <Routes>
          <Route path="/documents/:documentId" element={<DocumentDetailPage />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>
  );
}

describe("DocumentDetailPage summary", () => {
  it("renders document metadata from the API", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "report.pdf" })).toBeInTheDocument();
    expect(screen.getByText("application/pdf")).toBeInTheDocument();
    expect(screen.getAllByText("Completed").length).toBeGreaterThan(0);
    expect(screen.getByText("chunk text here")).toBeInTheDocument();
  });

  it("requests a summary and renders it with provider and sources", async () => {
    summarizeMock.mockResolvedValueOnce({
      document_id: "d1", filename: "report.pdf",
      summary: "This report covers quarterly results.",
      sources: [{ document_id: "d1", chunk_id: "c1", filename: "report.pdf", page_number: 1, score: null }],
      provider: "nvidia",
    });
    renderPage();
    const button = await screen.findByRole("button", { name: /summarize document/i });
    await userEvent.click(button);
    expect(summarizeMock).toHaveBeenCalledWith("d1");
    expect(await screen.findByText(/This report covers quarterly results/)).toBeInTheDocument();
    expect(screen.getByText("nvidia")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/Sources \(1\)/)).toBeInTheDocument());
  });

  it("shows a sanitized error when summarization fails", async () => {
    summarizeMock.mockRejectedValueOnce({
      isAxiosError: true,
      response: { status: 409, data: { detail: "Document has no chunks to summarize" } },
    });
    renderPage();
    await userEvent.click(await screen.findByRole("button", { name: /summarize document/i }));
    expect(await screen.findByText(/no chunks to summarize/i)).toBeInTheDocument();
  });
});
