import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DocumentsPage } from "../pages/DocumentsPage";
import { renderWithProviders } from "../test/test-utils";
import type { Document } from "../types";

vi.mock("../api/documents", () => ({
  documentsApi: {
    list: vi.fn().mockResolvedValue({ total: 2, items: [
      { id: "d1", file_name: "report.pdf", provider: "s3", processing_status: "completed",
        mime_type: "application/pdf", file_type: "pdf", file_size: 2048, created_at: "2026-01-01T10:00:00",
        modified_at: "2026-01-01T10:00:00" } as unknown as Document,
      { id: "d2", file_name: "notes.txt", provider: "google_drive", processing_status: "pending",
        mime_type: "text/plain", file_type: "txt", file_size: 100, created_at: "2026-01-02T10:00:00",
        modified_at: "2026-01-02T10:00:00" } as unknown as Document,
    ] }),
  },
}));

vi.mock("../api/files", () => ({ filesApi: { list: vi.fn().mockResolvedValue([]) } }));

describe("DocumentsPage", () => {
  it("renders the document list from the API", async () => {
    render(renderWithProviders(<DocumentsPage />).node);
    expect(await screen.findByText("report.pdf")).toBeInTheDocument();
    expect(screen.getByText("notes.txt")).toBeInTheDocument();
    expect(screen.getByText("2 total")).toBeInTheDocument();
    expect(screen.getAllByText("Completed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Pending").length).toBeGreaterThan(0);
  });

  it("shows the empty state when there are no documents", async () => {
    const { documentsApi } = await import("../api/documents");
    vi.mocked(documentsApi.list).mockResolvedValueOnce({ total: 0, items: [] });
    render(renderWithProviders(<DocumentsPage />).node);
    expect(await screen.findByText(/no documents yet/i)).toBeInTheDocument();
  });

  it("shows the error state when the API fails", async () => {
    const { documentsApi } = await import("../api/documents");
    vi.mocked(documentsApi.list).mockRejectedValueOnce({
      isAxiosError: true,
      response: { status: 500, data: { detail: "boom" } },
    });
    render(renderWithProviders(<DocumentsPage />).node);
    expect(await screen.findByText(/boom/i)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});
