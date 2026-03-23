import { motion } from "framer-motion";
import { Film, LayoutGrid, Search, Play } from "lucide-react";
import Badge from "../components/common/Badge";

const FEATURES = [
  {
    icon: LayoutGrid,
    title: "Grid & list views",
    desc: "Browse your collection with thumbnail cards or detailed lists",
  },
  {
    icon: Search,
    title: "Search & filter",
    desc: "Find videos by channel, tag, date, or full-text search",
  },
  {
    icon: Play,
    title: "Web player",
    desc: "Stream videos directly in your browser with keyboard shortcuts",
  },
];

export default function LibraryPage() {
  return (
    <div>
      {/* Hero */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="text-center py-12"
      >
        <Film
          size={48}
          className="mx-auto mb-5"
          style={{ color: "var(--accent-light)", opacity: 0.6 }}
        />
        <h1 className="text-2xl font-bold text-[var(--text-primary)] mb-2">
          Media library
        </h1>
        <p className="text-[var(--text-secondary)] max-w-lg mx-auto mb-5 text-sm leading-relaxed">
          Browse, search and stream your downloaded media. Card grid with
          thumbnails, filters by channel and tags, and a built-in video player.
        </p>
        <Badge variant="soon">Coming in Phase 2</Badge>
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
            <f.icon size={32} style={{ color: "var(--accent-light)" }} className="mb-3" />
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
