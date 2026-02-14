## 信息源可访问性分析（统一版）

### 1.1 可直接通过 RSS 获取的信息源 ✅

#### Track A — 一手源（官方/权威发布，48h 内发布自动入池）

| 信息源 | RSS地址 | 可用性 | 更新频率 | 内容类型 |
|--------|---------|--------|----------|----------|
| **OpenAI News** | https://openai.com/news/rss | ❌ 403 Forbidden | — | 降级为 Tavily `site:openai.com/news` |
| **Google DeepMind** | https://deepmind.google/blog/rss.xml | ✅ 可用 | 实时 | 研究论文、博客 |
| **arXiv AI** | https://rss.arxiv.org/rss/cs.AI | ✅ 可用 | 每日 | 学术论文 |
| **MIT Technology Review** | https://www.technologyreview.com/feed/ | ✅ 可用 | 实时 | 深度报道（仅取 AI 分类） |
| **Berkeley AI Research** | https://bair.berkeley.edu/blog/feed.xml | ✅ 可用 | 实时 | 学术研究 |
| **Import AI (Jack Clark)** | https://importai.substack.com/feed | ✅ 可用 | 每周 | 专家策展周刊 |
| **Hugging Face Blog** | https://huggingface.co/blog/feed.xml | ⚠️ 待复核 | 高频 | 开源模型生态与工程实践 |
| **Meta AI Blog** | https://ai.meta.com/blog/rss.xml | ⚠️ 待复核 | 实时 | 模型与研究发布 |
| **NVIDIA Blog** | https://feeds.feedburner.com/nvidiablog | ⚠️ 待复核 | 实时 | 基础设施与行业应用 |
| **Microsoft Research** | https://www.microsoft.com/en-us/research/feed/ | ⚠️ 待复核 | 实时 | 前沿研究发布 |
| **Apple ML Research** | https://machinelearning.apple.com/rss.xml | ⚠️ 待复核 | 不定期 | 端侧 AI 研究 |
| **AWS Machine Learning Blog** | https://aws.amazon.com/blogs/machine-learning/feed/ | ⚠️ 待复核 | 高频 | 云端 AI 工程实践 |

#### Track B — 二手源（社区/聚合，需过互动指标阈值入池）

| 信息源 | 地址 | 可用性 | 入池阈值 | 可用互动指标 |
|--------|------|--------|----------|--------------|
| **Hacker News AI** | https://hnrss.org/newest?q=AI+OR+LLM+OR+ChatGPT&points=50 | ✅ 可用 | Points >= 50 | Points, Comments（嵌入 description） |
| **HF Daily Papers** | https://papers.takara.ai/api/feed | ⚠️ 待复核 | Top 3 | Curated 排名 |
| **Tavily Search** | Tavily API | ✅ 可用 | score >= 0.75 | search relevance (0-1) |

### 1.2 需要通过其他方式获取的信息源

| 信息源 | 获取方式 | 可行方案 |
|--------|----------|----------|
| **Stanford HAI** | 网页结构 | 爬虫抓取 / 官方Newsletter订阅 |
| **The Batch (DeepLearning.AI)** | 邮件订阅 | 邮件解析 / 网页抓取 |
| **Stratechery** | 付费订阅 | 邮件解析 / RSS (付费会员) |
| **Lenny's Newsletter** | Substack | Substack RSS: https://www.lennysnewsletter.com/feed |
| **The Rundown AI** | 邮件订阅 | 邮件解析 / 网页抓取 |
| **Morning Brew** | 邮件订阅 | 邮件解析 |
| **SemiAnalysis** | 付费订阅 | 邮件解析 / RSS (付费会员) |

### 1.3 RSS 获取测试结果（2026-02-11 基线 + 待补充）

```
❌ OpenAI RSS        - 返回 403 Forbidden，需降级方案
✅ DeepMind RSS      - 正常返回 XML，包含最新文章
✅ arXiv AI RSS      - 正常返回 XML，每日更新
✅ MIT Tech Review   - 正常返回 XML，内容完整
✅ BAIR RSS          - 确认可用
✅ Import AI RSS     - 正常返回 XML，每周更新
✅ Hacker News AI    - 正常返回 XML，支持 &points=N 预过滤
⚠️ HF Blog / Meta / NVIDIA / MSR / Apple ML / AWS ML / HF Daily Papers - 待统一复测并回填
```

### 1.4 互动指标可用性

| 信源 | RSS 内含互动指标 | 说明 |
|------|------------------|------|
| Track A 全部源 | **无** | RSS 仅提供 title/link/pubDate/description，无 views/likes/shares |
| Hacker News | **Points + Comments** | 嵌入在 `<description>` 的 `<p>` 标签内，非独立 XML 字段 |
| Tavily | **search relevance score** | API 返回 0-1 分数，衡量与查询词匹配度，非文章热度 |
| HF Daily Papers | **Curated 排名** | 站点聚合排序，不等于跨站通用热度指标 |

> 设计决策：一手源（Track A）的价值由发布者权威性保证，不需要互动指标；
> 二手源（Track B）的价值由社区互动验证，必须过阈值。

---

### 1.5 Tavily 查询模板（Track B）

```
查询 1: "new AI model release benchmark 2026" (新模型发布+评测)
查询 2: "AI 新模型发布 能力评测 2026" (中文模型发布)
查询 3: "new AI application launch product release 2026" (新应用发布)
查询 4: "AI commercial deployment enterprise case study ROI 2026" (商业落地案例)
查询 5: "AI技术路线验证 商业落地 实际应用 2026" (中文商业落地)
查询 6: "LLM inference cost pricing update 2026" (推理成本/定价)
查询 7: "GitHub trending AI repositories today" (代码热点)
```

---

### 1.6 去重与排序策略

1. **URL 去重**：同一 URL 在 Track A / Track B 同时出现时，保留 Track A，合并 Track B 互动指标。
2. **事件去重**：同一事件多篇报道，仅保留信息密度最高的一篇。
3. **排序优先级**：
   - Track A 按 `published_at` 降序（新鲜度优先）
   - Track B 按 `hn_points` / `tavily_score` 降序（热度优先）

---

### 📋 信源分类（两轨制）

**Track A — 一手源（发布即入池）**:
- OpenAI News RSS（当前 403，降级 Tavily site search）
- Google DeepMind RSS
- arXiv AI RSS
- MIT Technology Review RSS（AI 分类过滤）
- Berkeley AI Research RSS
- Import AI (Substack RSS)
- Hugging Face Blog RSS
- Meta AI Blog RSS
- NVIDIA Blog RSS
- Microsoft Research RSS
- Apple ML Research RSS
- AWS Machine Learning Blog RSS

**Track B — 二手源（互动指标过阈值入池）**:
- Hacker News AI RSS（Points >= 50）
- HF Daily Papers（Top 3）
- Tavily Search（score >= 0.75）

**未接入（可选扩展）**:
- Stanford HAI（网页结构化抓取）
- The Batch（邮件解析）
- Stratechery（付费 RSS）
- Lenny's Newsletter（Substack RSS）
- The Rundown AI（邮件解析 / 网页抓取）
- Morning Brew（邮件解析）
- SemiAnalysis（付费订阅 / RSS）

---
