import { useState } from "react";
import { Outlet } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import Sidebar from "../components/common/Sidebar";
import MobileTabBar from "../components/common/MobileTabBar";

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="min-h-dvh flex">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />

      <main
        className="flex-1 transition-all duration-300 pb-20 md:pb-0"
        style={{ marginLeft: `var(--sidebar-w, 0px)` }}
      >
        {/* Dynamically set sidebar margin via CSS variable */}
        <style>{`
          @media (min-width: 768px) {
            main { --sidebar-w: ${collapsed ? 64 : 240}px; }
          }
        `}</style>

        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </div>
      </main>

      <MobileTabBar />
    </div>
  );
}
