import { memo } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const components: Components = {
  table: ({ children }) => (
    <div className="markdown-table-scroll" role="region" aria-label="方案表格" tabIndex={0}>
      <table>{children}</table>
    </div>
  ),
  a: ({ node: _node, href, children, ...props }) => href ? (
    <a {...props} href={href} target={href.startsWith("#") ? undefined : "_blank"} rel="noopener noreferrer">
      {children}
    </a>
  ) : <span>{children}</span>,
  // Model-generated image URLs must not initiate background requests or tracking.
  img: ({ src, alt }) => (
    <span className="markdown-image-link">
      图片：{alt || "未命名图片"}
      {src && <a href={src} target="_blank" rel="noopener noreferrer">查看图片</a>}
    </span>
  ),
};

export const MarkdownPreview = memo(function MarkdownPreview({ content }: { content: string }) {
  return (
    <div className="markdown-body" aria-label="方案 Markdown 预览">
      {/* Keep the default URL sanitizer; never enable raw HTML for generated content. */}
      <Markdown remarkPlugins={[remarkGfm]} skipHtml components={components}>
        {content}
      </Markdown>
    </div>
  );
});
