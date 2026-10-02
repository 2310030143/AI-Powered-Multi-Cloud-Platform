import { AxiosHeaders, type AxiosRequestConfig } from "axios";
import { describe, expect, it } from "vitest";
import { apiClient, getApiErrorMessage, TOKEN_STORAGE_KEY } from "../api/client";

// Directly exercise the registered request interceptor
const requestInterceptor = apiClient.interceptors.request["handlers"]![0].fulfilled as
  (config: AxiosRequestConfig) => AxiosRequestConfig;

describe("API client", () => {
  it("attaches the stored Bearer token to requests", () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, "test-token-123");
    const config = requestInterceptor({ headers: new AxiosHeaders() });
    expect(config.headers?.Authorization).toBe("Bearer test-token-123");
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  });

  it("sends no Authorization header without a stored token", () => {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    const config = requestInterceptor({ headers: new AxiosHeaders() });
    expect(config.headers?.Authorization).toBeUndefined();
  });

  it("extracts a string detail from API errors", () => {
    expect(getApiErrorMessage({ isAxiosError: true, response: { status: 404, data: { detail: "Document not found" } } } as never)).toBe(
      "Document not found"
    );
  });

  it("falls back to a friendly message when no detail exists", () => {
    expect(getApiErrorMessage({ isAxiosError: true, response: { status: 500, data: {} } } as never)).toContain(
      "HTTP 500"
    );
    expect(getApiErrorMessage(new Error("boom"))).toContain("Something went wrong");
  });
});
