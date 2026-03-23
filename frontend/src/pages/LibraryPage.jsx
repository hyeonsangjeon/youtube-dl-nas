import Badge from "../components/common/Badge";

export default function LibraryPage() {
  return (
    <div>
      <div className="flex items-center gap-3 mb-2">
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">
          Library
        </h1>
        <Badge variant="soon">Phase 2</Badge>
      </div>
      <p className="text-[var(--text-secondary)] mb-8">
        Browse and manage your downloaded media
      </p>

      <div className="glass-card p-16 text-center">
        <div className="text-5xl mb-4">📚</div>
        <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-2">
          Coming in Phase 2
        </h2>
        <p className="text-sm text-[var(--text-muted)] max-w-md mx-auto">
          Media library with thumbnails, search, filtering, and inline playback.
          Stay tuned!
        </p>
      </div>
    </div>
  );
}
