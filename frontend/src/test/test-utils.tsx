import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../context/AuthContext";

/** Wrap a node with the providers pages expect (router + auth). */
export function renderWithProviders(node: ReactNode) {
  return { node: <MemoryRouter><AuthProvider>{node}</AuthProvider></MemoryRouter> };
}
