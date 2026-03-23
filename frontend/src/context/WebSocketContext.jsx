import { createContext, useContext } from "react";
import { useAuth } from "./AuthContext";
import useWebSocket from "../hooks/useWebSocket";

const WebSocketContext = createContext();

export function WebSocketProvider({ children }) {
  const { isAuthenticated } = useAuth();
  const ws = useWebSocket(isAuthenticated);

  return (
    <WebSocketContext.Provider value={ws}>{children}</WebSocketContext.Provider>
  );
}

export function useWS() {
  const ctx = useContext(WebSocketContext);
  if (!ctx) throw new Error("useWS must be used within WebSocketProvider");
  return ctx;
}
