import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ReportsPage } from "../pages/ReportsPage";
import { renderWithProviders } from "../test/test-utils";

const generateMock = vi.fn();

vi.mock("../api/reports", () => ({
  reportsApi: { generate: (...args: unknown[]) => generateMock(...args) },
}));

vi.mock("../api/documents", () => ({
  documentsApi: {
    list: vi.fn().mockResolvedValue({
      total: 2,
      items: [
        { id: "d1", file_name: "a.pdf", provider: "s3", processing_status: "completed" },
        { id: "d2", file_name: "b.pdf", provider: "s3", processing_status: "completed" },
      ],
    }),
  },
}));

describe("ReportsPage", () => {
  it("renders all structured report sections from the API", async () => {
    generateMock.mockResolvedValueOnce({
      instruction: "Summarize both",
      report: {
        executive_summary: "The docs align.",
        key_findings: "- finding one",
        evidence: "a.pdf says so",
        recommendations: "Do the thing",
        conclusion: "All good",
      },
      sources: [{ document_id: "d1", chunk_id: "c1", filename: "a.pdf", page_number: 1, score: null }],
      provider: "ollama",
    });
    render(renderWithProviders(<ReportsPage />).node);

    // select documents from the picker
    await userEvent.click(await screen.findByLabelText(/a\.pdf/));
    await userEvent.click(screen.getByLabelText(/b\.pdf/));
    await userEvent.type(screen.getByLabelText(/report instruction/i), "Summarize both");
    await userEvent.click(screen.getByRole("button", { name: /generate report/i }));

    expect(generateMock).toHaveBeenCalledWith({ document_ids: ["d1", "d2"], instruction: "Summarize both" });
    expect(await screen.findByText(/The docs align/)).toBeInTheDocument();
    expect(screen.getByText("Key Findings")).toBeInTheDocument();
    expect(screen.getByText(/- finding one/)).toBeInTheDocument();
    expect(screen.getByText("Evidence")).toBeInTheDocument();
    expect(screen.getByText(/a\.pdf says so/)).toBeInTheDocument();
    expect(screen.getByText("Recommendations")).toBeInTheDocument();
    expect(screen.getByText(/Do the thing/)).toBeInTheDocument();
    expect(screen.getByText("Conclusion")).toBeInTheDocument();
    expect(screen.getByText("ollama")).toBeInTheDocument();
  });

  it("shows the backend error for an incomplete report (never a fabricated one)", async () => {
    generateMock.mockRejectedValueOnce({
      isAxiosError: true,
      response: { status: 502, data: { detail: "LLM returned an incomplete report — missing or empty sections: evidence" } },
    });
    render(renderWithProviders(<ReportsPage />).node);
    await userEvent.click(await screen.findByLabelText(/a\.pdf/));
    await userEvent.type(screen.getByLabelText(/report instruction/i), "make a report");
    await userEvent.click(screen.getByRole("button", { name: /generate report/i }));
    expect(await screen.findByText(/incomplete report/i)).toBeInTheDocument();
  });
});
