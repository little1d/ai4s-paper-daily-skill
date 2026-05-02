# ai4s-paper-daily-skill

面向 AI4S 的 **workflow-first 论文日报 skill / helper runner**。

- 先拿候选池
- 再按你的兴趣方向选出 **少量高相关论文**
- 对最终入选论文做 **全文门槛检查**
- 由当前 Codex / Claude **读完全文后**产出中文精读模板 + 毒舌点评 + 10 分制评分
- 写入 **飞书文档**
- 优先使用 **MinerU** 做 PDF 全文解析，并默认强制走 CPU，避免 Apple GPU / MPS 路径不稳定

## 当前首版边界

### 你真正会得到什么

每天一篇飞书日报，默认目标是：

- 总数 `<= 10` 篇
- 当天新论文优先 `3~5` 篇
- 不够的部分用 **历史优质论文池** 补齐
- 每篇都带：
  - 中文简介
  - 毒舌点评
  - 技术方案
  - 实验结果
  - 10 分评分

但注意：

- 最终精读不应该由规则模板直接生成
- helper script 负责：筛选 / 下载 / 解析 / 落盘
- 真正的精读由 skill 加载后的 LLM 自己读取 MinerU 结果后完成

## 数据流

```text
当天候选池 + 历史优质池
        ↓
相关性评分 / 配额控制
        ↓
最终入选论文
        ↓
全文读取门槛
        ↓
中文精读模板 + 评分
        ↓
飞书文档
```

## 候选来源

### 当天新论文流

当前首刀优先稳定：

- `papers.cool` 发现 arXiv 当天候选
- arXiv API 补元数据

> `bioRxiv / ChemRxiv` 仍可作为后续增强，但不抢第一版 workflow 主线。

### 历史优质论文流

首版采用 **curated pool**：

- 文件：`data/history_pool.json`

约束：

- 历史池里必须全是真实论文
- 不允许 `example.com / placeholder / Starter Pool`

这样做的原因是：

- 先把“历史优质论文补充”做稳
- 避免第一版一上来陷进复杂的全网历史检索

## 运行方式

### 1. dry-run（推荐先跑）

```bash
python .codex/skills/ai4s-paper-daily/scripts/ai4s_paper_daily.py \
  --date 2026-05-01 \
  --dry-run \
  --fixtures .codex/skills/ai4s-paper-daily/tests/fixtures \
  --output-root outputs/test-smoke-run
```

### 2. skill-first 准备运行

```bash
python .codex/skills/ai4s-paper-daily/scripts/ai4s_paper_daily.py \
  --date today \
  --output-root outputs/daily-runs \
  --history-pool data/history_pool.json \
  --fulltext-backend mineru \
  --extract-only
```

这一步会生成：

- `selected.json`
- `extraction_manifest.json`
- MinerU 解析产物

后续由 skill 读取这些文件，完成真正的 LLM 精读。


### 4. MinerU 模型缓存位置

默认会把 MinerU 相关模型缓存落到仓库内：

```text
.cache/mineru-models/
```

具体包括：

- `MODELSCOPE_CACHE=.cache/mineru-models/modelscope`

这样做的目的：

- 避免模型散落到全局用户目录
- 便于排查首次下载 / 缓存命中问题
- 配合 `.gitignore` 避免误提交大模型缓存

如果你确实要强制走 Hugging Face 缓存，直接显式设置 `HF_HOME` / `HUGGINGFACE_HUB_CACHE` 即可；脚本会优先尊重外部环境变量。默认情况下不会主动创建这两个目录。

## 输出目录

```text
OUTPUT_ROOT/
  YYYY-MM-DD/
    raw/
      today/
    cache/
      fulltexts/
    selected.json
    extraction_manifest.json
    reviewed.json
    reviewed/
      01_xxx.md
      02_xxx.md
      ...
    report.md
    publish.json
```

说明：

- `selected.json`：最终 shortlist（含相关性信息）
- `extraction_manifest.json`：给 skill / LLM 读全文时使用的解析清单（含 markdown、pdf、图片路径）
- `reviewed.json`：正式入选并完成全文门槛的论文
- `reviewed/*.md`：逐篇精读卡片
- `report.md`：最终日报 markdown
- `publish.json`：飞书写入结果

## 全文解析 backend

默认：

- `--fulltext-backend mineru`

含义：

- `mineru`

默认设备：

- `MINERU_DEVICE_MODE=cpu`

如果你确认本机别的设备路径稳定，可以显式覆盖。

## Skill 加载入口

仓库内正式 skill 文件：

```text
.codex/skills/ai4s-paper-daily/SKILL.md
```

它负责定义：

- 禁止虚构论文
- 如何调用 helper script
- 如何使用 MinerU 产物
- 如何让 Codex / Claude 自己读全文并写精读
- 如何把文档和图片写入飞书

## 如何触发这个 skill

最直接的触发方式是**显式点名**：

```text
$ai4s-paper-daily
```

例如你可以直接对 Codex / Claude 说：

```text
$ai4s-paper-daily 帮我做今天的 AI4S 论文速递
```

或者：

```text
$ai4s-paper-daily 先跑 extract-only，再基于 MinerU 全文生成飞书日报
```

如果你的运行环境支持自动加载仓库内 `.codex/skills/`，那么上面这种显式触发最稳。

### 推荐触发姿势

#### 方式 1：一步到位

```text
$ai4s-paper-daily 帮我生成今天的 AI4S 飞书论文日报，重点看 protein / docking / small-molecule / diffusion / flow matching
```

#### 方式 2：先解析，再精读

先执行：

```bash
python .codex/skills/ai4s-paper-daily/scripts/ai4s_paper_daily.py \
  --date today \
  --output-root outputs/daily-runs \
  --history-pool data/history_pool.json \
  --fulltext-backend mineru \
  --extract-only
```

然后对 Codex / Claude 说：

```text
$ai4s-paper-daily 请读取 outputs/daily-runs/YYYY-MM-DD/extraction_manifest.json，基于 MinerU 全文结果完成正式精读，并写入飞书文档
```

### 触发时建议说清楚的东西

可选补充：

- 日期：`today` / `2026-05-02`
- 方向偏好：`protein / small-molecule / docking / diffusion / flow matching / representation / post training`
- 产出方式：`doc-only`
- 是否先 `extract-only`
- 是否要求插入 MinerU 图片

如果你想强制只走 MinerU：

```bash
python .codex/skills/ai4s-paper-daily/scripts/ai4s_paper_daily.py \
  --date today \
  --output-root outputs/daily-runs \
  --history-pool data/history_pool.json \
  --fulltext-backend mineru
```

## Feishu 推送

脚本通过本地 `lark-cli docs +create / +update` 写飞书文档。

### 常用环境变量

- `FEISHU_DOC`：已有文档 token / URL；存在时更新同一文档
- `FEISHU_FOLDER_TOKEN`：创建到指定文件夹
- `FEISHU_WIKI_NODE`：创建到指定知识库节点
- `FEISHU_WIKI_SPACE`：创建到指定知识空间
- `FEISHU_TITLE_PREFIX`：文档标题前缀，默认 `AI4S 论文速递`

### 本地保存推荐

仓库根目录可放一个**不提交到 Git**的本地文件：

```text
.env.local
```

例如：

```bash
FEISHU_WIKI_NODE=JDm2w64FAi5MeVkmDyxcI1avnYd
FEISHU_TITLE_PREFIX=AI4S 论文速递
```

加载方式：

```bash
set -a
source .env.local
set +a
```

### 失败语义

- 默认：飞书失败 **不阻塞** 本地日报生成
- `--require-feishu`：飞书失败时返回非 0
- `--skip-feishu`：完全跳过飞书写入

## 测试

```bash
python -m unittest discover -s .codex/skills/ai4s-paper-daily/tests
```

## 文件说明

| 文件 | 说明 |
|---|---|
| `.codex/skills/ai4s-paper-daily/scripts/ai4s_paper_daily.py` | skill-local runner |
| `data/history_pool.json` | 历史优质论文 starter pool |
| `.codex/skills/ai4s-paper-daily/tests/fixtures/` | dry-run fixtures |
| `.codex/skills/ai4s-paper-daily/tests/` | relevance / selection / rendering / smoke tests |
