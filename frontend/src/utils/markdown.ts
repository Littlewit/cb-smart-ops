/**
 * Markdown 渲染工具：将 AI 回复的 Markdown 文本转为 HTML。
 *
 * 安全设计（面试可讲点）：
 * - `html: false` —— 输入中的 HTML 标签被转义为纯文本展示，
 *   AI 输出即使被提示词注入携带 <script> 也不会执行（XSS 防线一）
 * - `linkify: true` —— 纯 URL 自动转链接（markdown-it 会加 rel=noopener）
 * - 仅 AI 气泡使用 v-html；用户输入保持 {{ }} 纯文本插值（XSS 防线二）
 */
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({
  html: false, // 禁止内联 HTML（转义展示）
  linkify: true, // 自动识别裸链接
  breaks: true, // 单个换行转 <br>，贴合对话场景（LLM 输出常用单换行分点）
})

/**
 * 渲染 Markdown → HTML。
 * 空文本直接返回空串，避免流式首帧渲染出空 <p>。
 */
export function renderMarkdown(text: string): string {
  if (!text) return ''
  return md.render(text)
}
