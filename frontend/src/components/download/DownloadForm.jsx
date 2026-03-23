import { useState } from "react";
import { motion, useAnimation } from "framer-motion";
import { Link, Download, Subtitles } from "lucide-react";
import { createDownload } from "../../api/endpoints";

const RESOLUTIONS = [
  { value: "best", label: "Best quality" },
  { value: "1080p", label: "1080p" },
  { value: "720p", label: "720p" },
  { value: "480p", label: "480p" },
  { value: "360p", label: "360p" },
  { value: "144p", label: "144p" },
  { value: "audio-m4a", label: "Audio (M4A)" },
  { value: "audio-mp3", label: "Audio (MP3)" },
];

export default function DownloadForm() {
  const [url, setUrl] = useState("");
  const [resolution, setResolution] = useState("best");
  const [subtitles, setSubtitles] = useState(false);
  const [subFormat, setSubFormat] = useState("srt");
  const [subLang, setSubLang] = useState("en");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const shakeControls = useAnimation();

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");

    if (!url.trim()) {
      setError("Please enter a URL");
      shakeControls.start({
        x: [0, -8, 8, -6, 6, -3, 3, 0],
        transition: { duration: 0.4 },
      });
      return;
    }

    setLoading(true);
    try {
      const res = subtitles ? `${subFormat}|${subLang}` : resolution;
      await createDownload(url.trim(), res);
      setUrl("");
    } catch (err) {
      const msg = err.response?.data?.detail || "Failed to start download";
      setError(msg);
      shakeControls.start({
        x: [0, -8, 8, -6, 6, -3, 3, 0],
        transition: { duration: 0.4 },
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <motion.div animate={shakeControls}>
      <form
        onSubmit={handleSubmit}
        className="rounded-[var(--radius)] p-4 sm:p-5"
        style={{
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
        }}
      >
        {/* Main row */}
        <div className="flex flex-col md:flex-row gap-3">
          {/* URL input */}
          <div className="relative flex-1">
            <Link
              size={16}
              className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
            />
            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="Paste YouTube URL here..."
              className={`w-full pl-10 pr-4 py-2.5 rounded-[var(--radius-sm)] text-sm
                         bg-[var(--bg-input)] text-[var(--text-primary)]
                         placeholder:text-[var(--text-muted)] outline-none
                         transition-all duration-200
                         ${error ? "border-[var(--danger)] border" : "border border-[var(--border)] focus:border-[var(--accent)]"}`}
              style={{ boxShadow: "none" }}
              onFocus={(e) => {
                if (!error) e.target.style.boxShadow = "0 0 0 3px var(--accent-glow)";
              }}
              onBlur={(e) => { e.target.style.boxShadow = "none"; }}
            />
          </div>

          {/* Resolution select */}
          {!subtitles && (
            <select
              value={resolution}
              onChange={(e) => setResolution(e.target.value)}
              className="w-full md:w-[140px] px-3 py-2.5 rounded-[var(--radius-sm)] text-sm
                         bg-[var(--bg-input)] text-[var(--text-primary)]
                         border border-[var(--border)] outline-none cursor-pointer
                         focus:border-[var(--accent)] transition-colors"
            >
              {RESOLUTIONS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          )}

          {/* Download button */}
          <button
            type="submit"
            disabled={loading}
            className="w-full md:w-auto flex items-center justify-center gap-2 px-5 py-2.5
                       rounded-[var(--radius-sm)] text-sm font-semibold text-white
                       transition-all duration-200 cursor-pointer whitespace-nowrap
                       disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ background: "linear-gradient(135deg, #6c5ce7, #a29bfe)" }}
            onMouseEnter={(e) => {
              if (!loading) e.currentTarget.style.boxShadow = "0 4px 20px rgba(108,92,231,0.4)";
            }}
            onMouseLeave={(e) => { e.currentTarget.style.boxShadow = "none"; }}
          >
            {loading ? (
              <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <>
                <Download size={16} />
                Download
              </>
            )}
          </button>
        </div>

        {/* Subtitle toggle row */}
        <div className="flex items-center gap-4 mt-3">
          <label className="flex items-center gap-2 text-xs text-[var(--text-secondary)] cursor-pointer select-none">
            <button
              type="button"
              className="relative w-8 h-[18px] rounded-full transition-colors duration-200 cursor-pointer"
              style={{ background: subtitles ? "var(--accent)" : "var(--bg-input)" }}
              onClick={() => setSubtitles((v) => !v)}
            >
              <div
                className="absolute top-[2px] w-[14px] h-[14px] rounded-full bg-white transition-transform duration-200"
                style={{ left: subtitles ? 16 : 2 }}
              />
            </button>
            <Subtitles size={14} />
            Subtitles
          </label>

          {subtitles && (
            <div className="flex items-center gap-2">
              <select
                value={subFormat}
                onChange={(e) => setSubFormat(e.target.value)}
                className="px-2 py-1 text-xs rounded bg-[var(--bg-input)] text-[var(--text-primary)]
                           border border-[var(--border)] outline-none cursor-pointer"
              >
                <option value="srt">SRT</option>
                <option value="vtt">VTT</option>
              </select>
              <input
                type="text"
                value={subLang}
                onChange={(e) => setSubLang(e.target.value)}
                placeholder="en"
                className="w-14 px-2 py-1 text-xs rounded bg-[var(--bg-input)] text-[var(--text-primary)]
                           border border-[var(--border)] outline-none
                           focus:border-[var(--accent)] transition-colors"
              />
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <motion.p
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-xs text-[var(--danger)] mt-2"
          >
            {error}
          </motion.p>
        )}
      </form>
    </motion.div>
  );
}
