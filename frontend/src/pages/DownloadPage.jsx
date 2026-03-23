import { useCallback } from "react";
import { useWS } from "../context/WebSocketContext";
import ConnectionBanner from "../components/common/ConnectionBanner";
import DownloadForm from "../components/download/DownloadForm";
import ActiveDownload from "../components/download/ActiveDownload";
import DownloadQueue from "../components/download/DownloadQueue";
import HistoryTable from "../components/download/HistoryTable";

export default function DownloadPage() {
  const { isConnected, downloadState, currentDownload, history, setHistory } = useWS();

  const handleRemove = useCallback(
    (id) => setHistory((prev) => prev.filter((h) => h.id !== id)),
    [setHistory],
  );

  return (
    <div>
      <h1 className="text-2xl font-bold text-[var(--text-primary)] mb-1">
        Downloads
      </h1>
      <p className="text-[var(--text-secondary)] text-sm mb-6">
        Manage your download queue and history
      </p>

      <ConnectionBanner isConnected={isConnected} />

      <div className="flex flex-col gap-4">
        <DownloadForm />

        {currentDownload && (
          <ActiveDownload download={currentDownload} />
        )}

        <DownloadQueue queueSize={downloadState.queue_size} />

        <HistoryTable items={history} onRemove={handleRemove} />
      </div>
    </div>
  );
}
