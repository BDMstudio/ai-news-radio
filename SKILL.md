---
name: ai-news-radio
description: >
  每日自动搜集 AI 资讯，生成商业资讯文稿与 NotebookLM 风格双人对谈中文播客，并通过火山 TTS 合成音频。
  【执行时机】: Cron `0 7 * * *` 定时任务或手动调用时。
  【核心职责】: 负责采集、摘要、脚本与音频合成；不负责外部信源系统维护。
  【触发关键词】: "AI新闻", "播客生成", "TTS", "每日资讯"
allowed-tools: Read, Write, Glob, Grep, Bash, Tavily(search/extract), WebFetch
---

# AI News Radio Skill

---

## 硬性约束 (Critical Constraints)

| # | 规则 | 违规场景 | 正确做法 |
|---|------|----------|----------|
| C1 | **全文中文对话** | 输出英文脚本 | 播客脚本全中文，技术术语首次出现时附英文原名 |
| C2 | **英文信源必须翻译解读** | 直接朗读英文摘要 | 翻译为中文后用口语化方式讲解 |
| C3 | **中文语气词** | 使用 "Well", "You know" | 使用 "嗯...", "其实吧", "说白了", "怎么说呢" |
| C4 | **深度优先，不覆盖全部** | 泛泛而谈5条新闻 | 1篇 Deep Dive 讲透 + 2-3条快讯简述 |
| C5 | **零套话** | "让我们开始吧", "总的来说" | 直接进入话题，像朋友聊天 |
| C6 | **文稿必须含原文链接** | 无来源的二手摘要 | 每条资讯附原始 URL、来源名称 |
| C7 | **脚本 JSON 严格符合 Schema** | 自由发挥字段名 | 遵循 `templates/script_schema.json` 定义 |
| C8 | **单轮文本不超过 300 字符** | 长段独白 | 拆分为多轮对话，保持节奏 |
| C9 | **先报后评** | 上来就讨论观点 | 每条资讯必须先用 1-2 轮陈述事实（谁、做了什么、关键数据），再进入讨论 |
| C10 | **严格事实锚定 (Strict Grounding)** | 为了增加播客戏剧性，编造原文不存在的金额比例、亲属关系、测试数量等细节 | 仅允许使用输入数据中明确提供的事实。可以靠观点碰撞制造节目效果，严禁捏造事实 |
| C11 | **强制时序感知 (Temporal Awareness)** | 将几个月前的旧论文或文章描述为"这周刚发"、"今天的新闻" | 必须根据文章的 `published_at` 调整语气。对老文章必须用"前段时间"、"经典回顾"等表述自然引出 |
| C12 | **深度收束强制** | Deep Dive 只停留在"是什么/怎么看" | 最后 3 轮必须触及二阶效应、历史类比、实践者行动中至少两层 |

---

## 角色设定 (Characters)

### Alex (艾利克斯) - 主持人
- **人设**: 理性乐观派，对新技术充满好奇，前产品经理转科技记者
- **说话风格**: 善于用生活化类比解释技术概念，偶尔自嘲
- **标志性语气词**: "诶", "你看啊", "说白了", "打个比方", "这就很有意思了"
- **职责**: 引导话题、抛出问题、用类比降低理解门槛、控制节奏
- **TTS 发音人**: `zh_male_dayixiansheng_v2_saturn_bigtts`

### Jamie (杰米) - 技术专家 / 毒舌评论员
- **人设**: 斯多葛主义者，批判性思维强，讨厌炒作，前大厂架构师
- **说话风格**: 说话直率，爱泼冷水，偶尔冷幽默，引用具体数据反驳
- **标志性语气词**: "啧", "老实说", "不过啊", "说白了", "你仔细想想"
- **职责**: 深入技术细节、指出风险、提供内幕视角、拆解商业逻辑
- **TTS 发音人**: `zh_female_mizaitongxue_v2_saturn_bigtts`

---

## 工作流程 (Workflow)

### 输出目录规范（运行产物与技能包分离）
```
${AI_NEWS_RADIO_OUTPUT_ROOT:-./.skill-runs/ai-news-radio}/YYYYMMDD_HHmmss/
  raw_articles.json   # Phase 1 输出
  digest.md           # Phase 2 输出
  script.json         # Phase 3 输出
  podcast.mp3         # Phase 4 输出
```

- `SKILL.md/docs/config/scripts/templates` 属于技能包静态资产。
- `raw_articles.json/digest.md/script.json/podcast.mp3` 属于运行时产物，不应放入技能包目录。
- 如需归档，统一在输出根目录按时间戳管理。

示例（推荐）：

```bash
export AI_NEWS_RADIO_OUTPUT_ROOT="./.skill-runs/ai-news-radio"
mkdir -p "$AI_NEWS_RADIO_OUTPUT_ROOT"
```

---

### Phase 1: 资讯采集 (News Gathering)

**输入**: 无（自动触发）
**输出**: `${AI_NEWS_RADIO_OUTPUT_ROOT}/{timestamp}/raw_articles.json`
**工具**: Read, WebFetch (RSS), Tavily search/extract

#### 信源配置（统一文档）

信源不再写死在 `SKILL.md`，统一从 `docs/news_source_report.md` 读取。

- 唯一信源入口：`docs/news_source_report.md`
- 机器可读镜像：`config/sources.json`（由 `docs/news_source_report.md` 同步维护）
- Track A / Track B 的地址、阈值、降级策略都以该文档为准
- 若 `SKILL.md` 与信源文档冲突，以信源文档为准

#### 执行步骤

1. **读取信源配置** — 先读取 `docs/news_source_report.md`；如需结构化处理，再读取 `config/sources.json`。

2. **Track A 采集** — 遍历信源文档中的 Track A，提取最近 48 小时内文章：
   - 按文档中的地址逐个 WebFetch
   - MIT Technology Review 仅保留 `category` 含 "AI" / "Artificial intelligence" 的文章
   - OpenAI News 若 RSS 返回 403，改用 Tavily search `"site:openai.com/news"` 补充
   - 所有 Track A 文章自动入池，`source_track` 标记为 `"A"`

3. **Track B 采集** — 遍历信源文档中的 Track B，仅保留过阈值条目：
   - Hacker News：提取 Points 和 Comments，阈值按文档执行
   - HF Daily Papers：按文档规则取 Top N
   - Tavily Search：按文档查询词执行，仅保留 `score >= 0.75`
   - Track B 文章标记 `source_track` 为 `"B"`，附带原始互动指标

4. **Tavily extract** — 对候选池中最有价值的 3-5 篇文章提取全文内容

5. **去重与排序**：
   - **URL 去重**：同一 URL 在 Track A 和 Track B 同时出现时，保留 Track A 记录，合并 Track B 的互动指标
   - **排序规则**：
     - Track A 文章按 `published_at` 降序（最新优先）
     - Track B 文章按 `hn_points` 或 `tavily_score` 降序（热度优先）
     - 话题去重：同一事件的多篇报道只保留内容最深的一篇

6. **输出格式** — 保存为 `raw_articles.json`：
   ```json
   {
     "gathered_at": "ISO timestamp",
     "query_keywords": ["..."],
     "articles": [
       {
         "title": "原始标题",
         "source": "来源名称",
         "source_track": "A | B",
         "url": "原始链接",
         "published_at": "发布时间",
         "content": "全文内容（或摘要）",
         "category": "model_release | app_release | tech_validation | research | commercial_deployment | product | policy | opinion",
         "engagement": {
           "hn_points": null,
           "hn_comments": null,
           "tavily_score": null
         }
       }
     ]
   }
   ```
   - Track A 文章：`engagement` 字段全部为 `null`（不需要）
   - Track B 文章：填入实际指标值

#### 验收标准
- 至少获取 5 篇候选文章
- 每篇必须有 `url` 和 `source`
- 至少 **3 篇来自 Track A 一手源**
- Track B 文章必须附带至少一项非 null 的 `engagement` 指标

---

### Phase 2: 内容文稿 (Content Digest)

**输入**: `raw_articles.json`
**输出**: `${AI_NEWS_RADIO_OUTPUT_ROOT}/{timestamp}/digest.md`
**工具**: Read, Write

#### 执行步骤

1. **阅读原始文章** — 读取 `raw_articles.json`

2. **选题决策** — 从候选文章中选出：
   - **1 篇 Deep Dive**，按以下优先级（高→低）选择：
     1. `model_release` — 有 benchmark 对比或能力边界讨论
     2. `app_release` — 有明确用户场景和定价
     3. `tech_validation` — 有实际部署数据
     4. `commercial_deployment` — 有 ROI 或用户反馈
     5. `research` — 退回到有重大意义的论文
     6. `policy` / `opinion` — 仅在无其他可选时使用
   - **2-3 篇快讯**：其余有价值但不深入展开的资讯

3. **撰写文稿** — 按照 `templates/digest_template.md` 格式生成 `digest.md`：
   - Deep Dive 部分：中英双语标题、来源链接、精华解读（3-5段）、关键数据、延伸思考
   - 快讯部分：中文标题、来源链接、核心要点（2-3句）
   - 本期数据：文章来源分布、话题标签

4. **质量检查**：
   - 所有链接必须保留
   - 技术术语首次出现附英文
   - 事实核验：数据和事实必须 100% 来自原文。绝对禁止脑补或编造原文未提及的具体细节（如测试模型数量、捐款特定比例、人物亲属关系等）。
   - 时序打标：在整理每篇文章时，必须标注其发布时间距今的时差（如：距今 3 个月、昨日突发），为脚本生成提供时态依据。

#### 验收标准
- Deep Dive 精华解读不少于 500 字
- 每条资讯都有原文链接
- 技术术语有中英对照

---

### Phase 3: 播客脚本 (Script Generation)

**输入**: `digest.md`
**输出**: `${AI_NEWS_RADIO_OUTPUT_ROOT}/{timestamp}/script.json`
**工具**: Read, Write

#### 执行步骤

1. **读取文稿** — 读取 `digest.md` 获取整理后的资讯内容

2. **生成脚本** — 按照 `docs/podcast_prompt.md` 的角色设定和约束生成对话：

   **脚本结构设计**：
   ```
   [开场 2-3轮] 日常场景切入，自然连接到今天的技术话题
   [今日速览 3-4轮] Alex 快速播报本期所有资讯的一句话概要（类似新闻联播提要）
   [Deep Dive 15-20轮] 深度拆解（前 2 轮必须是事实铺垫，再进入讨论）：
     - Turn 1 (Alex): 陈述核心事实——谁发布了什么、解决什么问题、关键数据点
     - Turn 2 (Jamie): 补充技术上下文——这在行业里意味着什么、对比前代/竞品
     - Turn 3+: 进入讨论/辩论模式
       - Alex 用类比引出话题
       - Jamie 拆解技术细节
       - Alex 追问实际影响
       - Jamie 泼冷水指出风险
       - 双方就争议点展开辩论
       - 连接到更大的行业趋势
   [快讯 4-6轮] 每条: 1 轮事实概述 + 1 轮评论
   [收尾 2-3轮] 金句总结或冷幽默收场，不用模板化结尾
   ```

   **"今日速览"段落设计**：
   - Alex: "今天有几条消息挺有意思的，我先过一遍。第一条：[Deep Dive 标题一句话]。第二条/第三条：[快讯一句话]"
   - Jamie: 对最重磅的那条追加一句钩子（"这个我们等会儿得好好聊聊"）
   - 目的: 给听众建立心理地图，知道今天会聊什么，降低"突然聊到某个话题"的突兀感
   - 注意: 概述段允许单人连续 2-3 轮陈述，不受 X6 限制

   **时态与事实强约束 (Guardrails)**：
    - 时态映射法则：在撰写每条资讯对话时，必须核查文章的 published_at。若属于历史文章（相差 > 30 天），强制要求 Alex 和 Jamie 使用回顾性语气（例如："我突然想起之前那篇关于长程规划的研究"），严禁将其描述为"这周刚发"、"今天的大新闻"。
    - 事实防线 (Fact Lock)：允许 Jamie 毒舌批判，允许 Alex 幽默打比方，但绝对禁止让角色陈述原文 JSON 中不存在的客观实体细节（绝不可在台词中给自己“加戏”编造比例、数量或人物关系）。

   **Deep Dive 事实铺垫协议**：
   - Turn 1 (Alex): 陈述核心事实——谁发布了什么、解决什么问题、关键数据点
   - Turn 2 (Jamie): 补充技术上下文——这在行业里意味着什么、对比前代/竞品
   - Turn 3+: 进入讨论/辩论模式
   - 注意: 事实铺垫阶段允许单人连续 2 轮陈述，不受 X6 限制

   **快讯事实铺垫**：
   - 每条快讯第一轮必须是事实陈述（不是"对了还有条快讯"然后直接评论）
   - 第二轮才是 Jamie 的简短评价

3. **深度拆解框架** — 根据 Deep Dive 文章类型使用不同拆解角度：

   **论文/研究类**：
   - 解决了什么问题？之前为什么没人解决？
   - 核心方法是什么？（Alex 用类比，Jamie 补技术细节）
   - 实验结果怎么样？基准是否合理？
   - 局限性在哪？Jamie 必须指出

   **产品/发布类**：
   - 这东西到底干什么？谁会用？
   - 和竞品比怎么样？定价合理吗？
   - 商业模式说得通吗？
   - 什么情况下它会失败？

   **趋势/观点类**：
   - 数据支撑是否充分？
   - 反方观点是什么？
   - 历史上有类似的趋势吗？结果如何？
   - 普通人该怎么应对？

   **模型发布类 (Model Release)**：
   - 核心能力边界在哪？提升来源是算法突破还是算力堆叠？
   - 对现有技术栈（框架、工具链、部署方案）有什么冲击？
   - 定价和推理成本对不同规模开发者分别意味着什么？
   - Jamie 必须给"18个月后回头看"的预判

   **技术路线验证/商业落地类 (Tech Validation / Commercial Deployment)**：
   - 从论文到落地花了多久？落地瓶颈在哪？
   - 商业模型最脆弱的假设是什么？
   - 用户真实反馈 vs 官方宣传差距有多大？
   - Alex 必须给"如果我是创业者，我现在会..."的行动判断

4. **格式校验** — 确保 JSON 符合 `templates/script_schema.json`：
   - speaker 只能是 "Alex" 或 "Jamie"
   - emotion 使用标准枚举值
   - 单轮 text 不超过 300 字符
   - 总轮数 25-40 轮

#### 验收标准
- JSON 格式合法且符合 Schema
- Deep Dive 占总对话量 60% 以上
- 包含至少 2 次 Jamie 泼冷水/质疑
- 包含至少 1 个 Alex 的生活化类比
- 无模板化开场/结尾
- 单轮 text 均不超过 300 字符

---

### Phase 4: 语音合成 (TTS Generation)

**输入**: `script.json`
**输出**: `${AI_NEWS_RADIO_OUTPUT_ROOT}/{timestamp}/podcast.mp3`
**工具**: Bash (运行 Python 脚本)

#### 执行步骤

1. **环境检查** — 确认以下条件：
   ```bash
   # 1. 配置 API 凭证（编辑 .env 文件，填入真实值）
   #    文件位置: ai-news-radio/.env
   #    获取地址: https://console.volcengine.com/speech/service/10028
   cat .env

   # 2. 安装 Python 依赖（首次运行）
   pip install -r scripts/requirements.txt
   python3 -c "import websockets"
   ```
   脚本会自动从 `.env` 加载 `VOLC_APP_ID` 和 `VOLC_ACCESS_TOKEN`，无需手动 export。

2. **运行 TTS 脚本**：
   ```bash
    python3 scripts/generate_podcast.py \
      --script ${AI_NEWS_RADIO_OUTPUT_ROOT}/{timestamp}/script.json \
      --output ${AI_NEWS_RADIO_OUTPUT_ROOT}/{timestamp}/podcast.mp3
    ```

3. **验证输出**：
   - MP3 文件存在且大小 > 100KB
   - 无 TTS 错误日志

#### 验收标准
- MP3 文件生成成功
- 文件大小合理（通常 2-8 MB，对应 3-8 分钟音频）
- 无中断或截断

---

## 禁止事项 (Anti-patterns)

| # | 禁止 | 原因 |
|---|------|------|
| X1 | 流水账式罗列所有新闻 | 缺乏深度，听众无法获得洞见 |
| X2 | "大家好欢迎收听..." 模板开场 | AI 味太重，缺乏吸引力 |
| X3 | Alex 和 Jamie 互相吹捧 | 失去批判性，沦为软文 |
| X4 | 编造数据、来源或事实细节 | 商业资讯必须有据可查。严禁为了制造播客戏剧冲突，凭空捏造具体的金额比例、人物家属关系、参与测试的具体数量等原文中没有的内容。 |
| X5 | 脚本中使用英文整句 | 违反 C1 全中文约束 |
| X6 | 单人独白超过 3 轮（今日速览和事实铺垫段落例外，允许连续 2-3 轮） | 失去对话感，变成演讲 |
| X7 | 结尾使用 "感谢收听" 套话 | 用金句或冷幽默自然收场 |
| X8 | Deep Dive 话题只停留在表面 | 必须拆解到技术原理或商业逻辑层面 |
| X9 | 空降讨论——直接进入观点而不先陈述事实 | 听众不知道在讨论什么，信息密度为零 |
| X10 | 信源脱缰——引用不在信源清单中的来源 | 信源质量不可控，无法保证权威性 |
| X11 | 时空错乱 (Temporal Blindness) | 违背新闻逻辑。严禁无视 published_at，将几个月前的旧文章在剧本中描述为"今天刚发布"、"这周的突发"。 |
| X12 | Deep Dive 以"拭目以待"收束 | 零信息量懒惰收束，必须给出判断/行动建议/深刻开放问题 |

---

## 播客脚本最佳实践

基于 `example/podcast_example.json` 的优秀案例分析：

### 1. 开场技巧
- **从日常切入**: 用具体场景引发共鸣（如扫地机器人卡住→机器人学习物理）
- **制造悬念**: "我要告诉你一件稍微有点惊悚的事"
- **自然过渡**: 从现象连接到技术话题，不要硬转

### 2. 深度讨论技巧
- **层层递进**: 现象 → 技术解读 → 风险 → 解决方案
- **使用类比**: "就像给老房子装智能家居，不用拆墙布线"
- **引入数据**: "40,000 小时视频"、"提升 40%"
- **互相打断**: Jamie 在 Alex 说到一半时插入反驳，增加真实感

### 3. 收尾技巧
- **金句总结**: "欢迎来到 2026 年，真理是付费服务"
- **冷幽默**: "哪怕让你的'马屁精' Agent 帮你订阅也行"
- **开放式结尾**: 留下思考空间，不做定论

---

## 工具依赖

| 工具 | 用途 | 阶段 |
|------|------|------|
| Read | 读取统一信源文档 `docs/news_source_report.md` | Phase 1 Step 1 |
| WebFetch | 按信源文档采集 RSS | Phase 1 Step 2 |
| Tavily search | Track B 扩展搜索 + OpenAI 降级方案 | Phase 1 Step 3 |
| Tavily extract | 候选文章全文提取 | Phase 1 Step 4 |
| Read / Write | 文件读写 | Phase 2, 3 |
| Bash + Python | 火山 TTS 调用 | Phase 4 |

---

## 文件清单

```
ai-news-radio/
  SKILL.md                                # 本文件
  .env                                    # API 凭证配置（VOLC_APP_ID, VOLC_ACCESS_TOKEN）
  config/
    sources.json                          # 信源机器可读镜像（从 source_registry 同步）
    runtime.example.json                  # 运行时路径配置示例
  docs/
    news_source_report.md                 # 统一信源文档（唯一入口）
    podcast_prompt.md                     # 播客脚本生成 Prompt
    vocl_podcast_api.md                   # 火山 TTS API 文档
  templates/
    digest_template.md                    # 商业资讯文稿模板
    script_schema.json                    # 播客脚本 JSON Schema
  scripts/
    generate_podcast.py                   # 火山 TTS 客户端
    protocols.py                          # WebSocket 二进制协议
    requirements.txt                      # Python 依赖 (websockets)
  example/
    podcast_example.json                  # 优秀脚本范例

# 运行产物目录（不属于技能包）
./.skill-runs/ai-news-radio/
  {YYYYMMDD_HHmmss}/                      # 每次运行输出
    raw_articles.json
    digest.md
    script.json
    podcast.mp3
```
