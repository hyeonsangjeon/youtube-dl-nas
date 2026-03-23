import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Film } from "lucide-react";
import ProgressBar from "./ProgressBar";

export default function ActiveDownload({ download }) {
  const [visible, setVisible] = useState(true);

  // Auto-hide completed after 3s
  useEffect(() => {
    if (download?.status === "completed") {
      const t = setTimeout(() => setVisible(false), 3000);
      return () => clearTimeout(t);
    }
    setVisible(true);
  }, [download?.status]);

  if (!download || !visible) return null;

  const { title, channel, thumbnail_url, percent = 0, status, error } = download;
  const isFailed = status === "failed";
  const isComplete = status === "completed";
  const isMerging = status === "merging";

  function statusText() {
    if (isComplete) return "Completed!";
    if (isFailed) return "Failed";
    if (isMerging) return "Merging formats...";
    if (status === "downloading") return `${percent.toFixed(1)}%`;
    return "Starting...";
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.25 }}
        className="rounded-[var(--radius)] p-4"
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
        }}
      >
        <div className="flex gap-4 items-center">
          {/* Thumbnail */}
          {thumbnail_url ? (
            <img
              src={thumbnail_url}
              alt=""
              className="w-24 h-[54px] rounded-lg object-cover flex-shrink-0"
            />
          ) : (
            <div
              className="w-24 h-[54px] rounded-lg flex items-center justify-center flex-shrink-0"
              style={{ background: "var(--bg-input)" }}
            >
              <Film size={20} className="text-[var(--text-muted)]" />
            </div>
          )}

          {/* Info */}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-[var(--text-primary)] truncate">
              {title || "Getting video information..."}
            </p>
            <p className="text-xs text-[var(--text-secondary)] truncate mt-0.5">
              {channel || "Extracting metadata..."}
            </p>

            {/* Progress bar */}
            <div className="mt-2.5">
              <ProgressBar percent={percent} />
            </div>

            {/* Error message */}
            {isFailed && error && (
              <p className="text-xs text-[var(--danger)] mt-1 truncate">
                {error}
              </p>
            )}
          </div>

          {/* Status text */}
          <span
            className="text-sm font-mono font-medium flex-shrink-0"
            style={{
              color: isComplete
                ? "var(--success)"
                : isFailed
                  ? "var(--danger)"
                  : "var(--accent-light)",
            }}
          >
            {statusText()}
          </span>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
