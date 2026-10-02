import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LoginPage } from "../pages/LoginPage";
import { renderWithProviders } from "../test/test-utils";

vi.mock("../api/auth", () => ({
  authApi: {
    login: vi.fn().mockResolvedValue({ access_token: "tok", token_type: "bearer", expires_in: 3600 }),
    register: vi.fn(),
    me: vi.fn().mockResolvedValue({ id: "u1", name: "Test", email: "t@t.com", is_active: true, created_at: "2026-01-01" }),
  },
}));

describe("LoginPage", () => {
  it("renders the sign-in form with email and password fields", () => {
    render(renderWithProviders(<LoginPage />).node);
    expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeEnabled();
  });

  it("shows an API error when login fails", async () => {
    const { authApi } = await import("../api/auth");
    vi.mocked(authApi.login).mockRejectedValueOnce({
      isAxiosError: true,
      response: { status: 401, data: { detail: "Invalid email or password" } },
    });
    render(renderWithProviders(<LoginPage />).node);
    await userEvent.type(screen.getByLabelText(/email/i), "user@example.com");
    await userEvent.type(screen.getByLabelText(/password/i), "wrongpass");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/invalid email or password/i)).toBeInTheDocument();
  });
});
