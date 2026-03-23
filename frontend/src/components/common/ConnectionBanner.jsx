import { motion, AnimatePresence } from "framer-motion";
import { WifiOff } from "lucide-react";

export default function ConnectionBanner({ isConnected }) {
  return (
    <AnimatePresence>
      {!isConnected && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.25 }}
          className="flex items-center justify-center gap-2 px-4 py-2 text-sm rounded-[var(--radius-sm)] mb-4"
          style={{
            background: "rgba(254, 202, 87, 0.12)",
            border: "1px solid var(--warning)",
            color: "var(--warning)",
          }}
        >
          <WifiOff size={16} />
          <span>
            Connection lost. Reconnecting
            <span className="inline-block w-6 text-left animate-pulse">...</span>
          </span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
