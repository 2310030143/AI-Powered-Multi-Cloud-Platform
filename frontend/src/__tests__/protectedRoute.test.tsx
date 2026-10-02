import { render, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ProtectedRoute } from "../components/ProtectedRoute";
import { AuthProvider } from "../context/AuthContext";
import { TOKEN_STORAGE_KEY } from "../api/client";

function renderRoute() {
  return render(
    <AuthProvider>
      <MemoryRouterWrapper>
        <Routes>
          <Route path="/login" element={<div>login page</div>} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <div>secret area</div>
              </ProtectedRoute>
            }
          />
        </Routes>
      </MemoryRouterWrapper>
    </AuthProvider>
  );
}

// tiny helper so the test file stays self-contained
import { MemoryRouter } from "react-router-dom";
function MemoryRouterWrapper({ children }: { children: React.ReactNode }) {
  return <MemoryRouter initialEntries={["/"]}>{children}</MemoryRouter>;
}

describe("ProtectedRoute", () => {
  it("redirects unauthenticated users to the login page", async () => {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    renderRoute();
    expect(await screen.findByText(/login page/i)).toBeInTheDocument();
    expect(screen.queryByText(/secret area/i)).not.toBeInTheDocument();
  });
});
