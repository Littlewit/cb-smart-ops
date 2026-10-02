/**
 * 前端冒烟测试（Vitest + jsdom）：验证关键纯逻辑与基础挂载。
 * 完整的 E2E 走查由 Playwright 在部署验证阶段执行（计划任务 e2e-verify）。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { decodeRole } from '@/utils/jwt'
import { renderMarkdown } from '@/utils/markdown'

// 1) JWT payload 解码（Login.vue 中的 role 提取逻辑，抽到 utils 便于测试）
describe('JWT role 解码', () => {
  it('从 token payload 解出 role', () => {
    // 构造一个假 JWT：header.payload.signature（仅 payload 参与 base64 解码）
    const payload = Buffer.from(
      JSON.stringify({ sub: 'u1', role: 'operator', exp: 9999999999 })
    ).toString('base64url')
    const token = `eyJhbGciOiJIUzI1NiJ9.${payload}.sig`
    expect(decodeRole(token)).toBe('operator')
  })

  it('非法 token 兜底返回 viewer', () => {
    expect(decodeRole('not-a-jwt')).toBe('viewer')
  })
})

// 2) Markdown 渲染（AI 气泡）：粗体/列表转 HTML，HTML 注入被转义
describe('Markdown 渲染', () => {
  it('渲染粗体与列表', () => {
    const html = renderMarkdown('**预警等级**\n\n- 库存=0 → high')
    expect(html).toContain('<strong>预警等级</strong>')
    expect(html).toContain('<li>')
  })

  it('内联代码与空文本', () => {
    expect(renderMarkdown('`max(0, x)`')).toContain('<code>max(0, x)</code>')
    expect(renderMarkdown('')).toBe('')
  })

  it('HTML 注入被转义（html:false）', () => {
    const html = renderMarkdown('<script>alert(1)</script>')
    expect(html).not.toContain('<script>')
    expect(html).toContain('&lt;script&gt;')
  })
})

// 3) 基础挂载冒烟（验证 Vue 编译链路可用）
describe('App 挂载', () => {
  it('renders simple component', () => {
    const wrapper = mount({ template: '<div>ok</div>' })
    expect(wrapper.text()).toBe('ok')
  })
})
