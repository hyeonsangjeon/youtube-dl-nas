import { motion } from "framer-motion";
import { RefreshCw, Bell, HardDrive, Activity } from "lucide-react";

const FEATURES = [
  {
    icon: Bell,
    title: "Auto-collect",
    desc: "Set check intervals per channel, new videos download automatically",
  },
  {
    icon: HardDrive,
    title: "Full backup",
    desc: "Download all existing videos from a channel with rate limiting",
  },
  {
    icon: Activity,
    title: "Collection log",
    desc: "Real-time timeline of what's being detected and downloaded",
  },
];

export default function SubscriptionPage() {
  return (
    <div>
      {/* Hero */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="text-center py-12"
      >
        <RefreshCw
          size={48}
          className="mx-auto mb-5"
          style={{ color: "var(--success)", opacity: 0.6 }}
        />
        <h1 className="text-2xl font-bold text-[var(--text-primary)] mb-2">
          Channel subscriptions
        </h1>
        <p className="text-[var(--text-secondary)] max-w-lg mx-auto mb-5 text-sm leading-relaxed">
          Subscribe to YouTube channels and playlists. New videos are
          automatically downloaded on your schedule.
        </p>
        <span
          className="inline-flex items-center px-3 py-1 text-xs font-semibold uppercase tracking-wider
                     rounded-full border"
          style={{
            background: "rgba(0, 206, 201, 0.15)",
            color: "var(--success)",
            borderColor: "var(--success)",
          }}
        >
          Coming in Phase 3
        </span>
      </motion.div>

      {/* Feature cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {FEATURES.map((f, i) => (
          <motion.div
            key={f.title}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 + i * 0.1, duration: 0.3 }}
            className="p-6 rounded-[var(--radius)]"
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
            }}
          >
            <f.icon size={32} style={{ color: "var(--success)" }} className="mb-3" />
            <h3 className="font-semibold text-[var(--text-primary)] mb-1">
              {f.title}
            </h3>
            <p className="text-sm text-[var(--text-secondary)] leading-relaxed">
              {f.desc}
            </p>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
