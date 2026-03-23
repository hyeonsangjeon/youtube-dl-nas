import { motion } from "framer-motion";
import { Download, X, Film } from "lucide-react";
import Badge from "../common/Badge";
import { downloadFile, deleteHistory } from "../../api/endpoints";

function qualityBadge(resolution) {
  if (!resolution) return null;
  const r = resolution.toLowerCase();
  if (r === "best") return <Badge variant="success">BEST</Badge>;
  if (r.includes("audio")) return <Badge variant="warning">AUDIO</Badge>;
  if (r.match(/^\d+p$/)) return <Badge variant="default">{resolution.toUpperCase()}</Badge>;
  if (r.startsWith("srt") || r.startsWith("vtt")) return <Badge variant="default">SUB</Badge>;
  return <Badge>{resolution.toUpperCase()}</Badge>;
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function HistoryTable({ items, onRemove }) {
  if (!items || items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <Download size={48} className="text-[var(--text-muted)] opacity-30 mb-4" />
        <p className="text-[var(--text-secondary)] font-medium">
          No downloads yet
        </p>
        <p className="text-sm text-[var(--text-muted)] mt-1">
          Paste a URL above to get started
        </p>
      </div>
    );
  }

  async function handleDelete(id) {
    try {
      await deleteHistory(id);
      onRemove?.(id);
    } catch {
      // Silently fail — item may already be gone
    }
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
          Recent downloads
        </h2>
        <Badge variant="default">{items.length}</Badge>
      </div>

      <div className="flex flex-col gap-2">
        {items.map((item, i) => (
          <motion.div
            key={item.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.03, duration: 0.2 }}
            className="group flex items-center gap-3 p-3 rounded-[var(--radius-sm)]
                       transition-all duration-200 hover:translate-x-0.5"
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
            }}
          >
            {/* Thumbnail */}
            {item.thumbnail_url ? (
              <img
                src={item.thumbnail_url}
                alt=""
                className="hidden md:block w-16 h-9 rounded-md object-cover flex-shrink-0"
              />
            ) : (
              <div
                className="hidden md:flex w-16 h-9 rounded-md items-center justify-center flex-shrink-0"
                style={{ background: "var(--bg-input)" }}
              >
                <Film size={14} className="text-[var(--text-muted)]" />
              </div>
            )}

            {/* Info */}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-[var(--text-primary)] truncate">
                {item.title || item.url}
              </p>
              <div className="flex items-center gap-2 mt-0.5">
                {item.channel && (
                  <span className="text-xs text-[var(--text-secondary)] truncate">
                    {item.channel}
                  </span>
                )}
                {item.channel && item.resolution && (
                  <span className="text-[var(--text-muted)]">·</span>
                )}
                {qualityBadge(item.resolution)}
                {item.created_at && (
                  <>
                    <span className="text-[var(--text-muted)]">·</span>
                    <span className="text-xs text-[var(--text-muted)] whitespace-nowrap">
                      {formatDate(item.created_at)}
                    </span>
                  </>
                )}
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-1 flex-shrink-0 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
              {item.filename && (
                <button
                  onClick={() => downloadFile(item.id)}
                  className="p-2 rounded-[var(--radius-sm)] text-[var(--text-secondary)]
                             hover:text-[var(--accent-light)] hover:bg-[var(--accent-glow)]
                             transition-colors cursor-pointer"
                  title="Download file"
                >
                  <Download size={16} />
                </button>
              )}
              <button
                onClick={() => handleDelete(item.id)}
                className="p-2 rounded-[var(--radius-sm)] text-[var(--text-secondary)]
                           hover:text-[var(--danger)] hover:bg-red-500/10
                           transition-colors cursor-pointer"
                title="Remove from history"
              >
                <X size={16} />
              </button>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
