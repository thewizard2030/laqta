import React, { useState } from "react";
import { RefreshCw, Terminal, CheckCircle2 } from "lucide-react";
import { CapabilitiesResponse } from "../../../types/capabilities";
import { CapabilitiesCard } from "../../../components/CapabilitiesCard";
import { Button } from "../../../components/ui/Button";

interface SystemAuditTabProps {
  capabilities: CapabilitiesResponse;
  onRefreshCapabilities?: () => Promise<void> | void;
}

export const SystemAuditTab: React.FC<SystemAuditTabProps> = ({
  capabilities,
  onRefreshCapabilities,
}) => {
  const [refreshing, setRefreshing] = useState(false);
  const [refreshedAt, setRefreshedAt] = useState<string | null>(null);

  const handleRefresh = async () => {
    if (!onRefreshCapabilities) return;
    setRefreshing(true);
    try {
      await onRefreshCapabilities();
      setRefreshedAt(new Date().toLocaleTimeString());
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-3">
        <div className="flex items-center gap-2.5">
          <Terminal className="h-5 w-5 text-laqta-400" />
          <div>
            <h2 className="text-sm font-semibold text-white">System &amp; Engine Diagnostics</h2>
            <p className="text-xs text-slate-400">
              Live inspection of local binaries (FFmpeg, FFprobe), speech libraries, and hardware.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {refreshedAt && (
            <span className="text-[11px] text-emerald-400 flex items-center gap-1 font-mono">
              <CheckCircle2 className="h-3 w-3" />
              <span>Audited at {refreshedAt}</span>
            </span>
          )}
          {onRefreshCapabilities && (
            <Button
              variant="secondary"
              size="sm"
              loading={refreshing}
              onClick={handleRefresh}
              className="gap-1.5"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Re-probe Engine</span>
            </Button>
          )}
        </div>
      </div>

      <CapabilitiesCard capabilities={capabilities} />
    </div>
  );
};
