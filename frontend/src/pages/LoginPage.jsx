import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, useAnimation } from "framer-motion";
import { User, Lock, Eye, EyeOff, LogIn } from "lucide-react";
import { useAuth } from "../context/AuthContext";

export default function LoginPage() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const shakeControls = useAnimation();

  const [id, setId] = useState("");
  const [pw, setPw] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // If already authenticated, redirect
  if (isAuthenticated) {
    navigate("/", { replace: true });
    return null;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      await login(id, pw);
      navigate("/", { replace: true });
    } catch {
      setError("Invalid ID or password");
      shakeControls.start({
        x: [0, -12, 12, -8, 8, -4, 4, 0],
        transition: { duration: 0.5 },
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <motion.div animate={shakeControls}>
      <div
        className="rounded-[var(--radius)] p-8 sm:p-10"
        style={{
          background: "rgba(30, 32, 48, 0.8)",
          backdropFilter: "blur(20px)",
          border: "1px solid var(--border)",
        }}
      >
        {/* Logo */}
        <div className="text-center mb-8">
          <div
            className="inline-flex w-14 h-14 rounded-2xl items-center justify-center text-white text-2xl font-bold mb-5"
            style={{
              background:
                "linear-gradient(135deg, var(--accent), var(--accent-light))",
              boxShadow: "0 8px 32px rgba(108, 92, 231, 0.3)",
            }}
          >
            Y
          </div>
          <h1
            className="text-2xl font-bold"
            style={{ fontFamily: "var(--font-sans)" }}
          >
            <span className="text-white">youtube-dl</span>
            <span className="text-[var(--accent-light)]">-nas</span>
          </h1>
          <p className="text-sm text-[var(--text-secondary)] mt-1.5">
            Sign in to your media server
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {/* ID field */}
          <div className="relative">
            <User
              size={18}
              className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
            />
            <input
              type="text"
              value={id}
              onChange={(e) => setId(e.target.value)}
              placeholder="Username"
              autoComplete="username"
              required
              className="w-full pl-11 pr-4 py-3 rounded-[var(--radius-sm)] text-sm
                         bg-[var(--bg-input)] text-[var(--text-primary)]
                         border border-[var(--border)] outline-none
                         placeholder:text-[var(--text-muted)]
                         focus:border-[var(--accent)]
                         transition-all duration-200"
              style={{
                boxShadow: "none",
              }}
              onFocus={(e) =>
                (e.target.style.boxShadow =
                  "0 0 0 3px var(--accent-glow)")
              }
              onBlur={(e) => (e.target.style.boxShadow = "none")}
            />
          </div>

          {/* Password field */}
          <div className="relative">
            <Lock
              size={18}
              className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
            />
            <input
              type={showPw ? "text" : "password"}
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              placeholder="Password"
              autoComplete="current-password"
              required
              className="w-full pl-11 pr-11 py-3 rounded-[var(--radius-sm)] text-sm
                         bg-[var(--bg-input)] text-[var(--text-primary)]
                         border border-[var(--border)] outline-none
                         placeholder:text-[var(--text-muted)]
                         focus:border-[var(--accent)]
                         transition-all duration-200"
              style={{ boxShadow: "none" }}
              onFocus={(e) =>
                (e.target.style.boxShadow =
                  "0 0 0 3px var(--accent-glow)")
              }
              onBlur={(e) => (e.target.style.boxShadow = "none")}
            />
            <button
              type="button"
              onClick={() => setShowPw((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]
                         hover:text-[var(--text-secondary)] transition-colors cursor-pointer"
            >
              {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>

          {/* Error message */}
          {error && (
            <motion.p
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="text-sm text-[var(--danger)] text-center"
            >
              {error}
            </motion.p>
          )}

          {/* Submit button */}
          <button
            type="submit"
            disabled={loading}
            className="flex items-center justify-center gap-2 w-full py-3 mt-1
                       rounded-[var(--radius-sm)] text-sm font-semibold text-white
                       transition-all duration-200 cursor-pointer
                       disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background:
                "linear-gradient(135deg, #6c5ce7, #a29bfe)",
            }}
            onMouseEnter={(e) => {
              if (!loading)
                e.currentTarget.style.boxShadow =
                  "0 4px 20px rgba(108, 92, 231, 0.4)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.boxShadow = "none";
            }}
          >
            {loading ? (
              <span className="inline-block w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <>
                <LogIn size={18} />
                Sign In
              </>
            )}
          </button>
        </form>

        {/* Footer */}
        <p className="text-center text-xs text-[var(--text-muted)] mt-6">
          v2.0.0 — Powered by yt-dlp
        </p>
      </div>
    </motion.div>
  );
}
