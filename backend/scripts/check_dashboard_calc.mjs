/**
 * 临时诊断：用 Node 复现前端 totalSales 的计算链
 * （fetch API → 解包 data → reduce），对照 DB 真实值。验证后删除。
 */
const BASE = "http://localhost:8000";

// 1. 登录
const login = await fetch(`${BASE}/api/auth/login`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username: "admin", password: "admin123" }),
});
const { data: loginData } = await login.json();
const headers = { Authorization: `Bearer ${loginData.access_token}` };

// 2. 分别请求 7 天与 30 天口径
for (const days of [7, 30]) {
  const resp = await fetch(`${BASE}/api/dashboard/stats?days=${days}`, { headers });
  const { data } = await resp.json();
  const trend = data.sales_trend;
  // 与前端 totalSales 完全相同的 reduce 逻辑
  const totalSales = (trend || []).reduce((sum, d) => sum + Number(d.amount || 0), 0);
  console.log(
    `days=${days}: 点数=${trend.length} reduce合计=${totalSales.toFixed(2)} ` +
      `首日=${trend[0].date}:${trend[0].amount} 末日=${trend.at(-1).date}:${trend.at(-1).amount}`
  );
}
