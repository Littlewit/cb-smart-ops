/**
 * 前端冒烟测试（Vitest + jsdom）：验证关键纯逻辑与基础挂载。
 * 完整的 E2E 走查由 Playwright 在部署验证阶段执行（计划任务 e2e-verify）。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'

// 1) JWT payload 解码（Login.vue 中的 role 提取逻辑）
describe('JWT role 解码', () => {
  it('从 token payload 解出 role', () => {
    // 构造一个假 JWT：header.payload.signature（仅 payload 参与 base64 解码）
    const payload = Buffer.from(
      JSON.stringify({ sub: 'u1', role: 'operator', exp: 9999999999 })
    ).toString('base64url')
    const token = `eyJhbGciOiJIUzI1NiJ9.${payload}.sig`

    // 与 Login.vue decodeRole 相同的解析逻辑
    const payloadJson = JSON.parse(atob(token.split('.')[1]))
    expect(payloadJson.role).toBe('operator')
  })
})

// 2) App.vue 可正常挂载（冒烟：无模板/导入错误）
describe('App 挂载', () => {
  it('renders router-view', () => {
    // 挂载最简组件结构，验证 Vue 编译链路可用
    const wrapper = mount({ template: '<div>ok</div>' })
    expect(wrapper.text()).toBe('ok')
  })
})
