import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Shield } from "lucide-react";
import { api } from "@/lib/api";

export function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("nca");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.login(username, password);
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface-950 flex items-center justify-center">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-accent-blue/10 border border-accent-blue/30 mb-4">
            <Shield className="w-8 h-8 text-accent-blue" />
          </div>
          <h1 className="text-xl font-mono font-semibold tracking-wider text-surface-100">
            GAMEPREXDEF
          </h1>
          <p className="text-xs font-mono text-surface-400 mt-1 tracking-widest uppercase">
            National Command Authority Interface
          </p>
        </div>

        {/* Auth form */}
        <div className="panel p-6 space-y-4">
          <div className="text-center">
            <p className="text-2xs font-mono uppercase tracking-widest text-accent-amber">
              ⚠ CLASSIFIED // TOP SECRET
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="stat-label block mb-1">User ID</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full bg-surface-800 border border-surface-600 rounded px-3 py-2 text-sm font-mono text-surface-100 focus:outline-none focus:border-accent-blue"
                autoComplete="username"
              />
            </div>
            <div>
              <label className="stat-label block mb-1">Authentication Code</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-surface-800 border border-surface-600 rounded px-3 py-2 text-sm font-mono text-surface-100 focus:outline-none focus:border-accent-blue"
                autoComplete="current-password"
                placeholder="••••••••••••"
              />
            </div>

            {error && (
              <div className="px-3 py-2 bg-accent-red/10 border border-accent-red/30 rounded text-xs font-mono text-accent-red">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !password}
              className="w-full btn-primary py-2 justify-center"
            >
              {loading ? "Authenticating..." : "AUTHENTICATE"}
            </button>
          </form>

          <div className="pt-2 border-t border-surface-700">
            <p className="text-2xs font-mono text-surface-600 text-center">
              Default: nca / gameprex2024
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
