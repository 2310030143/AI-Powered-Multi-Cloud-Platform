import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatPage } from "../pages/ChatPage";
import { renderWithProviders } from "../test/test-utils";

const sendMock = vi.fn();

vi.mock("../api/chat", () => ({
  chatApi: { send: (...args: unknown[]) => sendMock(...args) },
}));

describe("ChatPage", () => {
  it("sends the message and renders the answer with sources", async () => {
    sendMock.mockResolvedValueOnce({
      message: "What is semantic search?",
      answer: "It retrieves content by meaning.",
      sources: [
        { document_id: "d1", chunk_id: "c1", filename: "notes.txt", page_number: 1, score: 0.55 },
      ],
    });
    render(renderWithProviders(<ChatPage />).node);
    await userEvent.type(screen.getByLabelText(/chat message/i), "What is semantic search?");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(sendMock).toHaveBeenCalledWith({ message: "What is semantic search?" });
    expect(await screen.findByText(/It retrieves content by meaning/)).toBeInTheDocument();
    expect(screen.getByText("notes.txt")).toBeInTheDocument();
    expect(screen.getByText(/score 0\.550/)).toBeInTheDocument();
  });

  it("shows an error when the chat API fails", async () => {
    sendMock.mockRejectedValueOnce({
      isAxiosError: true,
      response: { status: 503, data: { detail: "RAG is not configured" } },
    });
    render(renderWithProviders(<ChatPage />).node);
    await userEvent.type(screen.getByLabelText(/chat message/i), "hello");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(await screen.findByText(/RAG is not configured/i)).toBeInTheDocument();
  });
});
