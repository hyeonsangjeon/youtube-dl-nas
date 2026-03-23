import { NavLink } from "react-router-dom";
import { Download, Library, Rss, Settings } from "lucide-react";

const TABS = [
  { to: "/", icon: Download, label: "Downloads" },
  { to: "/library", icon: Library, label: "Library" },
  { to: "/subscriptions", icon: Rss, label: "Subs" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

export default function MobileTabBar() {
  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-30 flex items-center justify-around
                 h-16 border-t border-[var(--border)]"
      style={{
        background: "var(--sidebar-glass)",
        backdropFilter: "blur(20px)",
      }}
    >
      {TABS.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          className={({ isActive }) =>
            `flex flex-col items-center gap-1 px-3 py-1.5 rounded-lg transition-colors duration-200
             ${
               isActive
                 ? "text-[var(--accent-light)]"
                 : "text-[var(--text-muted)]"
             }`
          }
        >
          <Icon size={20} />
          <span className="text-[10px] font-medium">{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
