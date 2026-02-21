import { Shield, Check, X } from "lucide-react";

interface Props {
  message: string;
  send: (data: Record<string, unknown>) => void;
}

export function ToolApproval({ message, send }: Props) {
  const handleApprove = () => {
    // The actual approval ID comes from the WebSocket — this is a simplified version
    send({ type: "approve", approved: true });
  };

  const handleReject = () => {
    send({ type: "approve", approved: false });
  };

  return (
    <div className="flex gap-3 animate-fade-in">
      <div className="w-8 h-8 rounded-full bg-amber-500/20 flex items-center justify-center flex-shrink-0 animate-gentle-pulse">
        <Shield className="w-4 h-4 text-amber-400" />
      </div>
      <div className="max-w-2xl w-full">
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl px-4 py-3">
          <p className="text-sm text-amber-200 mb-3">{message}</p>
          <div className="flex gap-2">
            <button
              onClick={handleApprove}
              className="btn-success flex items-center gap-1.5 text-xs py-1.5 px-3"
            >
              <Check className="w-3.5 h-3.5" />
              Approve
            </button>
            <button
              onClick={handleReject}
              className="btn-danger flex items-center gap-1.5 text-xs py-1.5 px-3"
            >
              <X className="w-3.5 h-3.5" />
              Deny
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
