export default function ProgressBar({ percent = 0 }) {
  return (
    <div
      className="w-full h-1 rounded-full overflow-hidden"
      style={{ background: "var(--bg-input)" }}
    >
      <div
        className="h-full rounded-full"
        style={{
          width: `${Math.min(100, Math.max(0, percent))}%`,
          background: "linear-gradient(90deg, #6c5ce7, #a29bfe, #00cec9)",
          transition: "width 0.4s ease",
        }}
      />
    </div>
  );
}
