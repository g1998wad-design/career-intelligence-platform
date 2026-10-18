import { ShieldCheck } from "lucide-react";

export default function ConfidentialityNote({ note }: { note: string }) {
  return (
    <div className="flex gap-3 rounded-lg border border-border bg-surface px-5 py-4 text-sm text-muted">
      <ShieldCheck aria-hidden="true" size={18} className="mt-0.5 shrink-0 text-accent-cyan" />
      <p>{note}</p>
    </div>
  );
}
