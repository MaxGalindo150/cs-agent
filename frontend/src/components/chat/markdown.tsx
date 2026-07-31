"use client";

import {
  isValidElement,
  memo,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
import { Check, Copy } from "lucide-react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

// highlight.js dark theme; the code card neutralizes its background below.
import "highlight.js/styles/github-dark.css";

interface MarkdownProps {
  children: string;
}

/** Recursively flattens rendered children to a plain string (for copy). */
function nodeToText(node: ReactNode): string {
  if (node == null || node === false || node === true) return "";
  if (typeof node === "string") return node;
  if (typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(nodeToText).join("");
  if (isValidElement(node)) {
    return nodeToText((node.props as { children?: ReactNode }).children);
  }
  return "";
}

/** A fenced code block: language label + copy button over the highlighted code. */
function CodeBlock({
  language,
  code,
  children,
}: {
  language: string;
  code: string;
  children: ReactNode;
}) {
  const [copied, setCopied] = useState(false);

  function copy() {
    navigator.clipboard.writeText(code).then(
      () => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 2000);
      },
      () => {
        // Clipboard unavailable (e.g. insecure context) — ignore.
      },
    );
  }

  return (
    <div className="my-4 overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950">
      <div className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900 px-3 py-1.5">
        <span className="font-mono text-xs text-zinc-500">{language}</span>
        <button
          type="button"
          onClick={copy}
          className="flex items-center gap-1 text-xs text-zinc-500 transition-colors duration-150 hover:text-zinc-200"
        >
          {copied ? (
            <>
              <Check className="size-3.5" /> Copied
            </>
          ) : (
            <>
              <Copy className="size-3.5" /> Copy
            </>
          )}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 font-mono text-sm leading-relaxed [&_.hljs]:bg-transparent [&_.hljs]:p-0">
        {children}
      </pre>
    </div>
  );
}

const components: Components = {
  p({ children }) {
    return (
      <p className="my-4 text-[15px] leading-7 text-zinc-200 first:mt-0 last:mb-0">
        {children}
      </p>
    );
  },
  h1({ children }) {
    return (
      <h1 className="mt-8 mb-3 text-2xl font-semibold tracking-tight text-zinc-100 first:mt-0">
        {children}
      </h1>
    );
  },
  h2({ children }) {
    return (
      <h2 className="mt-7 mb-3 text-xl font-semibold tracking-tight text-zinc-100 first:mt-0">
        {children}
      </h2>
    );
  },
  h3({ children }) {
    return (
      <h3 className="mt-6 mb-2 text-lg font-semibold tracking-tight text-zinc-100 first:mt-0">
        {children}
      </h3>
    );
  },
  h4({ children }) {
    return (
      <h4 className="mt-5 mb-2 text-base font-semibold tracking-tight text-zinc-100 first:mt-0">
        {children}
      </h4>
    );
  },
  ul({ children }) {
    return (
      <ul className="my-4 list-disc space-y-1.5 pl-6 text-[15px] leading-7 text-zinc-200 marker:text-zinc-500">
        {children}
      </ul>
    );
  },
  ol({ children }) {
    return (
      <ol className="my-4 list-decimal space-y-1.5 pl-6 text-[15px] leading-7 text-zinc-200 marker:text-zinc-500">
        {children}
      </ol>
    );
  },
  li({ children }) {
    return <li className="pl-1">{children}</li>;
  },
  a({ href, children }) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-zinc-100 underline decoration-zinc-600 underline-offset-4 transition-colors duration-150 hover:decoration-zinc-300"
      >
        {children}
      </a>
    );
  },
  blockquote({ children }) {
    return (
      <blockquote className="my-4 border-l-2 border-zinc-700 pl-4 text-zinc-400 italic">
        {children}
      </blockquote>
    );
  },
  hr() {
    return <hr className="my-6 border-zinc-800" />;
  },
  table({ children }) {
    return (
      <div className="my-4 overflow-x-auto rounded-lg border border-zinc-800">
        <table className="w-full border-collapse text-sm">{children}</table>
      </div>
    );
  },
  th({ children }) {
    return (
      <th className="border border-zinc-800 bg-zinc-900 px-3 py-2 text-left font-medium text-zinc-200">
        {children}
      </th>
    );
  },
  td({ children }) {
    return (
      <td className="border border-zinc-800 px-3 py-2 text-zinc-300">
        {children}
      </td>
    );
  },
  code({ className, children }) {
    // Fenced blocks carry hljs / language-* classes (from rehype-highlight);
    // bare inline code has neither.
    const isBlock = /language-|hljs/.test(className ?? "");
    if (isBlock) {
      return <code className={className}>{children}</code>;
    }
    return (
      <code className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-[13px] text-zinc-200">
        {children}
      </code>
    );
  },
  pre({ children }) {
    const codeEl = isValidElement(children)
      ? (children as ReactElement<{ className?: string; children?: ReactNode }>)
      : null;
    const className = codeEl?.props.className ?? "";
    const language = /language-(\w+)/.exec(className)?.[1] ?? "text";
    const code = nodeToText(codeEl?.props.children).replace(/\n$/, "");
    return (
      <CodeBlock language={language} code={code}>
        {children}
      </CodeBlock>
    );
  },
};

/**
 * Renders assistant replies as GitHub-flavored Markdown with syntax-highlighted
 * code blocks. Raw HTML is NOT rendered (no rehype-raw), so this is XSS-safe.
 * react-markdown/remark tolerate partial input, so it renders progressively
 * during streaming without breaking. Memoized so re-renders only happen when
 * the text actually changes.
 */
function MarkdownImpl({ children }: MarkdownProps) {
  return (
    <div className="min-w-0">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={components}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

export const Markdown = memo(MarkdownImpl);
