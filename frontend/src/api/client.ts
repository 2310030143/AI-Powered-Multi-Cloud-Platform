import axios, { AxiosError } from "axios";

export const TOKEN_STORAGE_KEY = "file-intelligence-token";

// Relative by default: requests go through the Vite dev proxy to the local
// backend. Override with VITE_API_BASE_URL for a deployed backend.
export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) || "/api/v1";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

// Attach the JWT to every request
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Session expiry: clear credentials and return to the login page.
// (Full navigation is intentional here — the token is no longer valid.)
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      const currentPath = window.location.pathname + window.location.search;
      if (!currentPath.startsWith("/login")) {
        localStorage.removeItem(TOKEN_STORAGE_KEY);
        window.location.assign(`/login?next=${encodeURIComponent(currentPath)}`);
      }
    }
    return Promise.reject(error);
  }
);

/**
 * Extract a human-readable message from a backend/API error.
 * FastAPI validation errors surface as {detail: [...]}; everything else is
 * {detail: "..."}. Never exposes internals beyond what the API returned.
 */
export function getApiErrorMessage(error: unknown, fallback = "Something went wrong. Please try again."): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      if (first?.msg) return first.msg;
    }
    if (error.code === "ERR_NETWORK") {
      return "Cannot reach the backend. Is the API server running?";
    }
    if (error.response) {
      return `Request failed (HTTP ${error.response.status}).`;
    }
  }
  return fallback;
}
