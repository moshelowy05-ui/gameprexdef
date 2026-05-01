import { Routes, Route, Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { LoginPage } from "@/pages/LoginPage";
import { LobbyPage } from "@/pages/LobbyPage";
import { GamePage } from "@/pages/GamePage";

function AuthGuard({ children }: { children: React.ReactNode }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["me"],
    queryFn: () => api.me(),
    retry: false,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen bg-surface-950 flex items-center justify-center">
        <div className="text-xs font-mono text-surface-400 tracking-widest animate-pulse">
          AUTHENTICATING...
        </div>
      </div>
    );
  }

  if (isError || !data) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/"
        element={
          <AuthGuard>
            <LobbyPage />
          </AuthGuard>
        }
      />
      <Route
        path="/game/:gameId"
        element={
          <AuthGuard>
            <GamePage />
          </AuthGuard>
        }
      />
    </Routes>
  );
}
