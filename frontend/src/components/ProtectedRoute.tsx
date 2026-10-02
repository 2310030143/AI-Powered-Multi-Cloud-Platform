import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Loading } from "./States";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { token, initializing } = useAuth();
  const location = useLocation();

  if (initializing) {
    return <Loading label="Checking your session…" />;
  }
  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
}
