import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle, AlertCircle, AlertTriangle, X } from "lucide-react";

const ICONS = {
  success: CheckCircle,
  error: AlertCircle,
  warning: AlertTriangle,
};

const COLORS = {
  success: "var(--success)",
  error: "var(--danger)",
  warning: "var(--warning)",
};

export default function Toast({ message, type = "success", onClose }) {
  const [visible, setVisible] = useState(true);
  const Icon = ICONS[type] || ICONS.success;

  useEffect(() => {
    const t = setTimeout(() => {
      setVisible(false);
      setTimeout(() => onClose?.(), 300);
    }, 3000);
    return () => clearTimeout(t);
  }, [onClose]);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, x: 40 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 40 }}
          transition={{ duration: 0.25 }}
          className="fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3
                     rounded-[var(--radius-sm)] shadow-lg max-w-sm"
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
          }}
        >
          <Icon size={18} style={{ color: COLORS[type], flexShrink: 0 }} />
          <span className="text-sm text-[var(--text-primary)] flex-1">
            {message}
          </span>
          <button
            onClick={() => {
              setVisible(false);
              onClose?.();
            }}
            className="text-[var(--text-muted)] hover:text-[var(--text-secondary)]
                       transition-colors cursor-pointer flex-shrink-0"
          >
            <X size={14} />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
