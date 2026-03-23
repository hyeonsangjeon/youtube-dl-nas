import { useCallback, useEffect, useRef, useState } from "react";

const MAX_RETRIES = 10;
const RETRY_DELAY = 3000;

function getWsUrl() {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}

export default function useWebSocket(enabled = true) {
  const wsRef = useRef(null);
  const retriesRef = useRef(0);
  const timerRef = useRef(null);
  const shouldReconnectRef = useRef(true);

  const [isConnected, setIsConnected] = useState(false);
  const [downloadState, setDownloadState] = useState({
    is_downloading: false,
    current_download_id: null,
    queue_size: 0,
  });
  const [currentDownload, setCurrentDownload] = useState(null);
  const [history, setHistory] = useState([]);

  const handleMessage = useCallback((event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }

    const { type, data } = msg;

    switch (type) {
      case "state":
        setDownloadState({
          is_downloading: data.is_downloading,
          current_download_id: data.current_download_id,
          queue_size: data.queue_size,
        });
        if (data.current_download_id) {
          setCurrentDownload((prev) => prev || {
            download_id: data.current_download_id,
            title: null,
            channel: null,
            thumbnail_url: null,
            percent: 0,
            status: "downloading",
          });
        } else {
          setCurrentDownload(null);
        }
        break;

      case "history_item":
        setHistory((prev) => {
          if (prev.some((h) => h.id === data.id)) return prev;
          return [...prev, data];
        });
        break;

      case "history_complete":
        // History batch is done — no action needed
        break;

      case "metadata":
        setCurrentDownload((prev) => ({
          ...prev,
          download_id: data.download_id,
          title: data.title,
          channel: data.channel,
          thumbnail_url: data.thumbnail_url,
        }));
        setDownloadState((prev) => ({
          ...prev,
          is_downloading: true,
          current_download_id: data.download_id,
        }));
        break;

      case "progress":
        setCurrentDownload((prev) => ({
          ...prev,
          download_id: data.download_id,
          percent: data.percent,
          status: data.status,
        }));
        break;

      case "complete":
        setDownloadState((prev) => ({
          ...prev,
          is_downloading: false,
          current_download_id: null,
        }));
        setCurrentDownload((prev) => prev ? {
          ...prev,
          status: "completed",
          percent: 100,
          filename: data.filename,
        } : null);
        setTimeout(() => setCurrentDownload(null), 3000);
        // Refresh history from server
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          setHistory([]);
          wsRef.current.send(JSON.stringify({ type: "request_history" }));
        }
        break;

      case "failed":
        setDownloadState((prev) => ({
          ...prev,
          is_downloading: false,
          current_download_id: null,
        }));
        setCurrentDownload((prev) => prev ? {
          ...prev,
          status: "failed",
          error: data.error,
        } : null);
        setTimeout(() => setCurrentDownload(null), 5000);
        break;
    }
  }, []);

  const connectRef = useRef(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(getWsUrl());

    ws.onopen = () => {
      setIsConnected(true);
      retriesRef.current = 0;
    };

    ws.onmessage = handleMessage;

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;

      if (shouldReconnectRef.current && retriesRef.current < MAX_RETRIES) {
        retriesRef.current += 1;
        timerRef.current = setTimeout(() => connectRef.current?.(), RETRY_DELAY);
      }
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, [handleMessage]);

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  const sendMessage = useCallback((msg) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    shouldReconnectRef.current = true;
    connect();
    return () => {
      shouldReconnectRef.current = false;
      clearTimeout(timerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [enabled, connect]);

  return { isConnected, downloadState, currentDownload, history, setHistory, sendMessage };
}
