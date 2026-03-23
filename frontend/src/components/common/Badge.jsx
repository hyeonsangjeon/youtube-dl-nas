export default function Badge({ children, variant = "default" }) {
  const styles = {
    default:
      "bg-[var(--accent-glow)] text-[var(--accent-light)] border-[var(--accent)]",
    success: "bg-emerald-500/10 text-[var(--success)] border-[var(--success)]",
    danger: "bg-red-500/10 text-[var(--danger)] border-[var(--danger)]",
    warning: "bg-yellow-500/10 text-[var(--warning)] border-[var(--warning)]",
    soon: "bg-[var(--accent-glow)] text-[var(--accent-light)] border-[var(--accent)]",
  };

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider
                  rounded-full border ${styles[variant] || styles.default}`}
    >
      {children}
    </span>
  );
}
