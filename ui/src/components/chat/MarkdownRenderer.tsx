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
    <div className="my-2 bg-gray-900 rounded-lg overflow-hidden border border-gray-800 group/code">
      <div className="flex items-center justify-between px-3 py-1 bg-gray-800/50 border-b border-gray-800">
        <span className="text-[10px] text-gray-500 font-mono">
          {lang || "code"}
        </span>
        <button
          onClick={handleCopy}
          className="text-gray-500 hover:text-gray-300 transition-colors"
          title="Copy code"
        >
          {copied ? (
            <Check className="w-3 h-3 text-emerald-400" />
          ) : (
            <Copy className="w-3 h-3" />
          )}
        </button>
      </div>
      <pre className="px-3 py-2 text-xs font-mono text-gray-300 overflow-x-auto">
        <code>{code}</code>
      </pre>
    </div>
  );
}

const components: Components = {
  // Headings
  h1: ({ children }) => (
    <h1 className="text-xl font-bold text-gray-100 mt-4 mb-2 pb-1 border-b border-gray-700/50">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-lg font-bold text-gray-100 mt-3 mb-2 pb-1 border-b border-gray-800/50">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-base font-semibold text-gray-100 mt-3 mb-1">
      {children}
    </h3>
  ),
  h4: ({ children }) => (
    <h4 className="text-sm font-semibold text-gray-200 mt-2 mb-1">
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

  // Paragraphs
  p: ({ children }) => (
    <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>
  ),

  // Bold and italic
  strong: ({ children }) => (
    <strong className="font-semibold text-gray-100">{children}</strong>
  ),
  em: ({ children }) => <em className="italic text-gray-300">{children}</em>,

  // Links
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

  // Lists
  ul: ({ children }) => (
    <ul className="list-disc list-outside ml-5 mb-2 space-y-0.5">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal list-outside ml-5 mb-2 space-y-0.5">
      {children}
    </ol>
  ),
  li: ({ children }) => (
    <li className="text-gray-200 leading-relaxed pl-1">{children}</li>
  ),

  // Code
  code: ({ className, children, ...props }) => {
    const isBlock = className?.includes("language-") || String(children).includes("\n");

    if (isBlock) {
      return <CodeBlock className={className}>{children}</CodeBlock>;
    }

    // Inline code
    return (
      <code className="px-1.5 py-0.5 bg-gray-700 rounded text-plutus-300 text-xs font-mono">
        {children}
      </code>
    );
  },

  // Pre — just pass through, code block handles styling
  pre: ({ children }) => <>{children}</>,

  // Blockquotes
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-plutus-500/40 pl-3 my-2 text-gray-400 italic">
      {children}
    </blockquote>
  ),

  // Horizontal rule
  hr: () => <hr className="my-3 border-gray-700/50" />,

  // Tables
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto rounded-lg border border-gray-800">
      <table className="w-full text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-gray-800/50">{children}</thead>
  ),
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => (
    <tr className="border-b border-gray-800/50 last:border-0">{children}</tr>
  ),
  th: ({ children }) => (
    <th className="px-3 py-1.5 text-left font-semibold text-gray-300">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-1.5 text-gray-400">{children}</td>
  ),

  // Images
  img: ({ src, alt }) => (
    <img
      src={src}
      alt={alt || ""}
      className="max-w-full rounded-lg my-2 border border-gray-800"
    />
  ),

  // Task lists (GFM)
  input: ({ checked, ...props }) => (
    <input
      type="checkbox"
      checked={checked}
      readOnly
      className="mr-1.5 accent-plutus-500 rounded"
      {...props}
    />
  ),

  // Strikethrough
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
