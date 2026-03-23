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
    return undefined;
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
        <div className="flex flex-col sm:flex-row gap-4 sm:items-center">
          {/* Thumbnail */}
          {thumbnail_url ? (
            <img
              src={thumbnail_url}
              alt=""
              className="w-full sm:w-24 h-auto sm:h-[54px] rounded-lg object-cover flex-shrink-0"
            />
          ) : (
            <div
              className="w-full sm:w-24 h-[120px] sm:h-[54px] rounded-lg flex items-center justify-center flex-shrink-0"
              style={{ background: "var(--bg-input)" }}
            >
              <Film size={20} className="text-[var(--text-muted)]" />
            </div>
          )}

          {/* Info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-medium text-[var(--text-primary)] truncate">
                {title || "Getting video information..."}
              </p>
              {!isFailed && (
                <span
                  className="text-sm font-mono font-medium flex-shrink-0"
                  style={{
                    color: isComplete ? "var(--success)" : "var(--accent-light)",
                  }}
                >
                  {statusText()}
                </span>
              )}
            </div>
            <p className="text-xs text-[var(--text-secondary)] truncate mt-0.5">
              {channel || "Extracting metadata..."}
            </p>

            {/* Progress bar */}
            <div className="mt-2.5">
              <ProgressBar percent={percent} />
            </div>

            {/* Failed badge + error */}
            {isFailed && (
              <div className="mt-2 flex items-start gap-2">
                <span
                  className="inline-flex items-center px-2 py-0.5 text-[10px] font-semibold uppercase
                             tracking-wider rounded-full flex-shrink-0"
                  style={{
                    background: "rgba(255, 107, 107, 0.12)",
                    color: "var(--danger)",
                    border: "1px solid var(--danger)",
                  }}
                >
                  Failed
                </span>
                {error && (
                  <p className="text-xs text-[var(--danger)] leading-snug">
                    {error}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
