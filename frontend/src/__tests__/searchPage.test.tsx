import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SearchPage } from "../pages/SearchPage";
import { renderWithProviders } from "../test/test-utils";

const searchMock = vi.fn();

vi.mock("../api/search", () => ({
  searchApi: { search: (...args: unknown[]) => searchMock(...args) },
}));

describe("SearchPage", () => {
  it("sends the query to the API and renders scored results", async () => {
    searchMock.mockResolvedValueOnce({
      query: "semantic search",
      total: 1,
      results: [
        {
          score: 0.8123, chunk_id: "c1", chunk_index: 0, page_number: 2,
          content: "Semantic search finds content by meaning.",
          token_count: 42, document_id: "d1", file_name: "notes.txt",
          mime_type: "text/plain", source: "s3",
        },
      ],
    });
    render(renderWithProviders(<SearchPage />).node);
    await userEvent.type(screen.getByLabelText(/search query/i), "semantic search");
    await userEvent.click(screen.getByRole("button", { name: /search/i }));
    expect(searchMock).toHaveBeenCalledWith(expect.objectContaining({ query: "semantic search" }));
    expect(await screen.findByText("notes.txt")).toBeInTheDocument();
    expect(screen.getByText("0.812")).toBeInTheDocument();
    expect(screen.getByText(/Semantic search finds content by meaning/)).toBeInTheDocument();
  });

  it("shows the empty-results state", async () => {
    searchMock.mockResolvedValueOnce({ query: "nothing", total: 0, results: [] });
    render(renderWithProviders(<SearchPage />).node);
    await userEvent.type(screen.getByLabelText(/search query/i), "nothing");
    await userEvent.click(screen.getByRole("button", { name: /search/i }));
    expect(await screen.findByText(/no matching content found/i)).toBeInTheDocument();
  });
});
