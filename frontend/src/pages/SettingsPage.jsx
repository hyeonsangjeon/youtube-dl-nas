import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Palette,
  Server,
  Info,
  Sun,
  Moon,
  ExternalLink,
} from "lucide-react";
import { useTheme } from "../context/ThemeContext";
import { useWS } from "../context/WebSocketContext";
import Badge from "../components/common/Badge";

function SettingRow({ label, children }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-[var(--border)] last:border-b-0">
      <span className="text-sm text-[var(--text-secondary)]">{label}</span>
      <div className="text-sm text-[var(--text-primary)]">{children}</div>
    </div>
  );
}

function SectionCard({ icon: Icon, title, delay = 0, children }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.3 }}
      className="p-6 rounded-[var(--radius)]"
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
      }}
    >
      <div className="flex items-center gap-2 mb-4">
        <Icon size={18} style={{ color: "var(--accent-light)" }} />
        <h2 className="font-semibold text-[var(--text-primary)]">{title}</h2>
      </div>
      {children}
    </motion.div>
  );
}

export default function SettingsPage() {
  const { theme, toggle } = useTheme();
  const { isConnected } = useWS();
  const isDark = theme === "dark";

  const [apiStatus, setApiStatus] = useState("checking");

  useEffect(() => {
    fetch("/api/health")
      .then((r) => {
        setApiStatus(r.ok ? "connected" : "disconnected");
      })
      .catch(() => {
        setApiStatus("disconnected");
      });
  }, []);

  return (
    <div>
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <h1 className="text-2xl font-bold text-[var(--text-primary)] mb-1">
          Settings
        </h1>
        <p className="text-sm text-[var(--text-secondary)] mb-6">
          Configure your server and preferences
        </p>
      </motion.div>

      <div className="flex flex-col gap-4">
        {/* Appearance */}
        <SectionCard icon={Palette} title="Appearance" delay={0.05}>
          <SettingRow label="Dark mode">
            <button
              onClick={toggle}
              className="flex items-center gap-2 cursor-pointer"
            >
              {isDark ? (
                <Moon size={16} style={{ color: "var(--accent-light)" }} />
              ) : (
                <Sun size={16} style={{ color: "var(--warning)" }} />
              )}
              <div
                className="relative w-10 h-[22px] rounded-full transition-colors duration-200"
                style={{ background: isDark ? "var(--accent)" : "var(--bg-input)" }}
              >
                <div
                  className="absolute top-[3px] w-4 h-4 rounded-full bg-white transition-transform duration-200"
                  style={{ left: isDark ? 21 : 3 }}
                />
              </div>
            </button>
          </SettingRow>
        </SectionCard>

        {/* System */}
        <SectionCard icon={Server} title="System" delay={0.15}>
          <SettingRow label="Download path">
            <span className="font-mono text-xs text-[var(--text-muted)]">
              /downfolder
            </span>
          </SettingRow>
          <SettingRow label="API status">
            {apiStatus === "checking" ? (
              <span className="text-xs text-[var(--text-muted)]">Checking…</span>
            ) : apiStatus === "connected" ? (
              <Badge variant="success">Connected</Badge>
            ) : (
              <Badge variant="danger">Disconnected</Badge>
            )}
          </SettingRow>
          <SettingRow label="WebSocket">
            {isConnected ? (
              <Badge variant="success">Connected</Badge>
            ) : (
              <Badge variant="danger">Disconnected</Badge>
            )}
          </SettingRow>
        </SectionCard>

        {/* About */}
        <SectionCard icon={Info} title="About" delay={0.25}>
          <SettingRow label="Application">
            <span className="font-semibold">youtube-dl-nas</span>
          </SettingRow>
          <SettingRow label="Version">
            <span className="font-mono text-xs">v2.0.0</span>
          </SettingRow>
          <SettingRow label="Stack">
            <span className="text-xs">FastAPI + React + yt-dlp</span>
          </SettingRow>
          <SettingRow label="Source">
            <a
              href="https://github.com/hyeonsangjeon/youtube-dl-nas"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-[var(--accent-light)]
                         hover:underline transition-colors"
            >
              <ExternalLink size={14} />
              <span className="text-xs">View on GitHub</span>
            </a>
          </SettingRow>
        </SectionCard>
      </div>
    </div>
  );
}
