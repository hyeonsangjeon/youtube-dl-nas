import { NavLink } from "react-router-dom";
import {
  Download,
  Library,
  Rss,
  Settings,
  PanelLeftClose,
  PanelLeft,
} from "lucide-react";
import ThemeToggle from "./ThemeToggle";
import Badge from "./Badge";

const NAV_ITEMS = [
  { to: "/", icon: Download, label: "Downloads" },
  { to: "/library", icon: Library, label: "Library", badge: "Soon" },
  { to: "/subscriptions", icon: Rss, label: "Subscriptions", badge: "Soon" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

export default function Sidebar({ collapsed, onToggle }) {
  return (
    <aside
      className="glass-sidebar hidden md:flex flex-col fixed inset-y-0 left-0 z-30 transition-all duration-300"
      style={{ width: collapsed ? 64 : 240 }}
    >
      {/* Logo */}
      <div className="flex items-center h-16 px-4 gap-3 border-b border-[var(--border)]">
        <div
          className="flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center font-bold text-white text-sm"
          style={{ background: "linear-gradient(135deg, var(--accent), var(--accent-light))" }}
        >
          Y
        </div>
        {!collapsed && (
          <span className="font-semibold text-sm text-[var(--text-primary)] whitespace-nowrap">
            youtube-dl-nas
          </span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 flex flex-col gap-1 px-3 py-4">
        {NAV_ITEMS.map(({ to, icon: Icon, label, badge }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-sm)] transition-all duration-200 group relative
               ${
                 isActive
                   ? "bg-[var(--accent-glow)] text-[var(--accent-light)]"
                   : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--border-hover)]"
               }`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-[var(--accent)]" />
                )}
                <Icon size={20} className="flex-shrink-0" />
                {!collapsed && (
                  <span className="text-sm font-medium whitespace-nowrap flex-1">
                    {label}
                  </span>
                )}
                {!collapsed && badge && <Badge variant="soon">{badge}</Badge>}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Bottom controls */}
      <div className="px-3 pb-4 flex flex-col gap-1 border-t border-[var(--border)] pt-3">
        <ThemeToggle collapsed={collapsed} />
        <button
          onClick={onToggle}
          className="flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-sm)] w-full
                     text-[var(--text-secondary)] hover:text-[var(--text-primary)]
                     hover:bg-[var(--border-hover)] transition-all duration-200 cursor-pointer"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <PanelLeft size={20} /> : <PanelLeftClose size={20} />}
          {!collapsed && (
            <span className="text-sm font-medium whitespace-nowrap">
              Collapse
            </span>
          )}
        </button>
      </div>
    </aside>
  );
}
