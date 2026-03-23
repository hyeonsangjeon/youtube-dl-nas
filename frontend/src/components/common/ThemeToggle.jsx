import { Sun, Moon } from "lucide-react";
import { useTheme } from "../../context/ThemeContext";

export default function ThemeToggle({ collapsed }) {
  const { theme, toggle } = useTheme();
  const isDark = theme === "dark";

  return (
    <button
      onClick={toggle}
      className="flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-sm)] w-full
                 text-[var(--text-secondary)] hover:text-[var(--text-primary)]
                 hover:bg-[var(--border-hover)] transition-all duration-200 cursor-pointer"
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
    >
      {isDark ? <Sun size={20} /> : <Moon size={20} />}
      {!collapsed && (
        <span className="text-sm font-medium whitespace-nowrap">
          {isDark ? "Light mode" : "Dark mode"}
        </span>
      )}
    </button>
  );
}
