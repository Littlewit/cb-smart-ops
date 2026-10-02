"""临时核对：按本地时区统计各时间窗订单总额（对照看板数字后删除）。"""
import sqlite3
from datetime import datetime, timedelta

now = datetime.now()
c = sqlite3.connect("dev.db")

for days in (7, 30):
    since = (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    row = c.execute(
        "select count(*), round(sum(amount), 2) from orders where created_at >= ?",
        (since,),
    ).fetchone()
    print(f"近{days}天(本地时区): {row}")

total = c.execute("select count(*), round(sum(amount), 2) from orders").fetchone()
print("全部订单:", total)

# 各日分布（30 天，看是否有 0 天）
rows = c.execute(
    "select substr(created_at, 1, 10) d, round(sum(amount), 2) a "
    "from orders group by d order by d"
).fetchall()
print("有订单的天数:", len(rows), "/ 最小单日额:", min(r[1] for r in rows))
