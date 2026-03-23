import { motion } from "framer-motion";

export default function DownloadQueue({ queueSize = 0 }) {
  if (queueSize <= 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-2 px-4 py-2.5 rounded-[var(--radius-sm)] text-sm"
      style={{
        background: "var(--accent-glow)",
        border: "1px solid var(--border)",
      }}
    >
      <div
        className="w-2 h-2 rounded-full animate-pulse"
        style={{ background: "var(--accent-light)" }}
      />
      <span className="text-[var(--text-secondary)]">
        <span className="font-mono font-medium text-[var(--accent-light)]">
          {queueSize}
        </span>{" "}
        {queueSize === 1 ? "item" : "items"} in queue
      </span>
    </motion.div>
  );
}
