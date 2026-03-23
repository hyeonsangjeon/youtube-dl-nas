export default function LoginPage() {
  return (
    <div className="glass-card p-8">
      <div className="text-center mb-8">
        <div
          className="inline-flex w-14 h-14 rounded-2xl items-center justify-center text-white text-2xl font-bold mb-4"
          style={{
            background:
              "linear-gradient(135deg, var(--accent), var(--accent-light))",
          }}
        >
          Y
        </div>
        <h1 className="text-xl font-bold text-[var(--text-primary)]">
          youtube-dl-nas
        </h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">
          Sign in to your media server
        </p>
      </div>

      <p className="text-center text-sm text-[var(--text-muted)]">
        Login form coming in next sprint
      </p>
    </div>
  );
}
