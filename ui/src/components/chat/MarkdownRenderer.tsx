import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import { Copy, Check } from "lucide-react";

interface Props {
  content: string;
}

function CodeBlock({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  const [copied, setCopied] = useState(false);
  const match = /language-(\w+)/.exec(className || "");
  const lang = match ? match[1] : "";
  const code = String(children).replace(/\n$/, "");

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="my-3 bg-gray-950 rounded-xl overflow-hidden border border-gray-800/80">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-900/80 border-b border-gray-800/50">
        <span className="text-[11px] text-gray-500 font-mono">
          {lang || "code"}
        </span>
        <button
          onClick={handleCopy}
          className="text-gray-500 hover:text-gray-300 transition-colors"
          title="Copy code"
        >
          {copied ? (
            <Check className="w-3.5 h-3.5 text-emerald-400" />
          ) : (
            <Copy className="w-3.5 h-3.5" />
          )}
        </button>
      </div>
      <pre className="px-4 py-3 text-[13px] font-mono text-gray-300 overflow-x-auto leading-relaxed">
        <code>{code}</code>
      </pre>
    </div>
  );
}

const components: Components = {
  h1: ({ children }) => (
    <h1 className="text-xl font-semibold text-gray-100 mt-5 mb-2 pb-1.5 border-b border-gray-800/50">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-lg font-semibold text-gray-100 mt-4 mb-2 pb-1 border-b border-gray-800/40">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-base font-semibold text-gray-100 mt-3 mb-1">
      {children}
    </h3>
  ),
  h4: ({ children }) => (
    <h4 className="text-sm font-semibold text-gray-200 mt-2.5 mb-1">
      {children}
    </h4>
  ),
  h5: ({ children }) => (
    <h5 className="text-sm font-medium text-gray-200 mt-2 mb-1">{children}</h5>
  ),
  h6: ({ children }) => (
    <h6 className="text-xs font-medium text-gray-300 mt-2 mb-1 uppercase tracking-wide">
      {children}
    </h6>
  ),

  p: ({ children }) => (
    <p className="mb-2.5 last:mb-0 leading-relaxed">{children}</p>
  ),

  strong: ({ children }) => (
    <strong className="font-semibold text-gray-100">{children}</strong>
  ),
  em: ({ children }) => <em className="italic text-gray-300">{children}</em>,

  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-plutus-400 hover:text-plutus-300 underline underline-offset-2 decoration-plutus-400/30 hover:decoration-plutus-300/50 transition-colors"
    >
      {children}
    </a>
  ),

  ul: ({ children }) => (
    <ul className="list-disc list-outside ml-5 mb-3 space-y-1">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal list-outside ml-5 mb-3 space-y-1">
      {children}
    </ol>
  ),
  li: ({ children }) => (
    <li className="text-gray-200 leading-relaxed pl-1">{children}</li>
  ),

  code: ({ className, children, ...props }) => {
    const isBlock = className?.includes("language-") || String(children).includes("\n");

    if (isBlock) {
      return <CodeBlock className={className}>{children}</CodeBlock>;
    }

    return (
      <code className="px-1.5 py-0.5 bg-gray-800/80 border border-gray-700/40 rounded-md text-plutus-300 text-[13px] font-mono">
        {children}
      </code>
    );
  },

  pre: ({ children }) => <>{children}</>,

  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-plutus-500/30 pl-4 my-3 text-gray-400 italic">
      {children}
    </blockquote>
  ),

  hr: () => <hr className="my-4 border-gray-800/50" />,

  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-xl border border-gray-800">
      <table className="w-full text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-gray-900/60">{children}</thead>
  ),
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => (
    <tr className="border-b border-gray-800/50 last:border-0">{children}</tr>
  ),
  th: ({ children }) => (
    <th className="px-3 py-2 text-left font-semibold text-gray-300">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-2 text-gray-400">{children}</td>
  ),

  img: ({ src, alt }) => (
    <img
      src={src}
      alt={alt || ""}
      className="max-w-full rounded-xl my-3 border border-gray-800"
    />
  ),

  input: ({ checked, ...props }) => (
    <input
      type="checkbox"
      checked={checked}
      readOnly
      className="mr-1.5 accent-plutus-500 rounded"
      {...props}
    />
  ),

  del: ({ children }) => (
    <del className="text-gray-500 line-through">{children}</del>
  ),
};

export function MarkdownRenderer({ content }: Props) {
  return (
    <div className="markdown-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
