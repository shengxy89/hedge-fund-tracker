# 13F Alpha Tracker — Dashboard 文档

## 快速启动

```bash
# 进入项目目录
cd hedge_fund_tracker

# 启动 Streamlit
streamlit run dashboard/app.py
```

默认访问 http://localhost:8501

---

## 7 大视图概览

### 1. Overview 首页
30 秒看完整体市场态势：
- **4 个 KPI 卡**：追踪基金数、总持仓市值（环比）、NEW 建仓数、最拥挤股票
- **Top 10 净买入/净卖出**：横向柱状图，颜色区分 sector
- **板块轮动**：11 GICS sector × 最近 4 季度堆叠面积图
- **基金活跃度排行**：按调仓笔数排序

### 2. Heatmap 热力图
双模式切换：
- **Position Changes**：Y=基金 × X=股票，颜色编码 NEW/ADD/HOLD/REDUCE/SOLD
  - 三层过滤：最少持有基金数（1/2/3/5/10）→ Top N（10/30/50/100）→ 排序方式
- **Sector Weights**：Y=基金 × X=11 GICS Sector，Blues 连续色阶

### 3. Fund Drill-down 基金穿透
4 个 Tab：
- **Overview**：总市值、持仓数、Top 10 集中度、换手率 + filing 信息
- **Holdings**：完整持仓表（可搜索、按市值筛选、ProgressColumn 显示 weight%）
- **Position Changes**：4 分卡 NEW/SOLD/ADD/REDUCE + Top 5 历史趋势
- **Sector Allocation**：饼图对比 + 板块时序折线

### 4. Stock Drill-down 个股穿透
- **搜索**：支持 ticker / name / CUSIP 模糊匹配（≥2 字符）
- **KPI**：持有基金数、总市值、总股数、拥挤度排名
- **3 列布局**：左（持有人列表）、中（历史堆叠图）、右（拥挤度分析）
- **情绪指标**：NEW/SOLD/ADD/REDUCE 计数 + 净流入/流出判断
- **Jaccard**：持有该股票的基金间趋同度

### 5. Crowding Leaderboard 拥挤度排行
- **All Sectors**：Top 50 主表，ProgressColumn 显示 crowding_score
- **By Sector**：11 个子 Tab 分组查看
- **Rising/Falling**：上升最快 / 下降最快双卡

### 6. Options Positions 期权专属
- **KPI**：CALL/PUT 名义市值、Put-Call Ratio、持有期权基金数
- **CALL / PUT 双 Tab**：Top 20 标的表 + Top 10 条形图
- 数据与 Soros 等基金实际期权持仓一致

### 7. Compare Funds 基金对比
- **两个基金下拉选择**
- **Common Holdings**：交集列表（含双方 shares/value/weight%）
- **Jaccard Trend**：最近 8 季度趋同度折线
- **Co-Moves**：共同 ADD / 共同 REDUCE
- **Reverse Actions**：一方 NEW 另一方 SOLD 的反向操作高亮

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | Streamlit ≥ 1.35 |
| 图表库 | Plotly ≥ 5.22 (express + graph_objects) |
| 数据查询 | Pandas + SQLAlchemy `text()` |
| 数据库 | SQLite (`StaticPool`, `check_same_thread=False`) |
| 缓存 | `@st.cache_data(ttl=3600)` |
| Lint | ruff |

---

## 文件结构

```
dashboard/
├── app.py                          # 主入口：7 个 Tab 路由
├── data_access.py                  # 数据层：18 个查询函数 + 8 个新增
├── theme.py                        # 配色 + Plotly 模板 + CSS 注入
├── utils/
│   ├── formatters.py               # 数字格式化：$1.2B / 12.3% / +5.6%
│   └── exporters.py                # CSV 导出
├── components/
│   ├── filters.py                  # 侧边栏：季度/基金/Sector/刷新/重置
│   ├── charts.py                   # Plotly 封装：pie/line/bar/heatmap/area
│   ├── kpi_cards.py                # 4 列 KPI 指标卡
│   ├── disclaimer.py               # SOLD 说明 / PUT-CALL 图例 / 延迟徽章
│   └── data_quality_badge.py       # 覆盖率 / 国际股标识
└── views/
    ├── overview.py                 # View 0: 宏观看板
    ├── heatmap.py                  # View 1: 调仓 + 板块双模式热力图
    ├── fund_drill.py               # View 2: 基金穿透 4 Tab
    ├── stock_drill.py              # View 3: 个股穿透 + 搜索 + 情绪
    ├── crowding_leaderboard.py     # View 4: 拥挤度排行
    ├── options_view.py             # View 5: PUT/CALL 期权专属
    └── compare_funds.py            # View 6: 基金两两对比
```

---

## 关键设计决策

1. **PUT/CALL 隔离**：默认所有视图过滤 `put_call IS NULL OR '' OR 'NONE'`，期权在专属 Tab 展示
2. **无 Ticker 国际股**：`COALESCE(ticker, LEFT(name, 12))` + 🌐 标识，tooltip 显示完整 name + CUSIP
3. **SOLD 免责声明**：每个涉及 SOLD 的视图底部均有阈值说明（"可能降至 $25M 以下"）
4. **数据延迟徽章**：report_date vs filing_date 双显示，标注 lag days

---

## 自测清单

- [x] Overview KPI 数值与 SQL 手算一致
- [x] 热力图三层过滤全部生效
- [x] Fund Drill 4 Tab 切换正常
- [x] Stock Drill 搜索 "ASML" 正确显示国际股
- [x] Options CALL/PUT 数量与 Soros 数据吻合
- [x] Fund Compare Berkshire vs Tiger Global Jaccard 正常
- [x] 所有视图均有数据延迟徽章
- [x] ruff check dashboard/ 零报错
- [x] 所有函数有 type hints + docstring
