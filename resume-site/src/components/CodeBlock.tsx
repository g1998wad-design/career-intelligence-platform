import type { CodeSample } from "@/types/project";

export default function CodeBlock({ title, language, code }: CodeSample) {
  return (
    <figure className="overflow-hidden rounded-lg border border-border bg-surface">
      <figcaption className="flex items-center justify-between border-b border-border px-4 py-2 text-xs text-muted">
        <span className="font-medium text-text">{title}</span>
        <span className="font-mono uppercase tracking-wide">{language}</span>
      </figcaption>
      <pre className="overflow-x-auto p-4 text-sm leading-relaxed">
        <code className="font-mono text-[#d7e3f4]">{code}</code>
      </pre>
    </figure>
  );
}
