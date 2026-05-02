---
name: ai4s-paper-daily
description: "AI4S 论文日报 skill：helper script 负责选篇/MinerU/飞书，最终精读由当前 LLM 读全文后生成，禁止虚构论文。"
---

# AI4S Paper Daily Skill

把一个 **workflow-first 的论文日报流程**落到 AI4S，但**最终精读必须由当前 LLM 自己读全文后写出来**，不是靠规则模板硬抽。

## 目标

每天产出一份飞书 AI4S 论文日报：

- 总数 `<= 10`
- 当天新论文优先 `3~5`
- 不够再补历史优质论文
- 最终只保留**高相关 + 有全文 + 值得读**的论文
- 每篇输出中文精读笔记、毒舌点评、评分
- 发布到飞书文档 / 知识库

## 硬约束

### 1. 禁止虚构

- 禁止编造论文
- 禁止使用 `example.com`
- 禁止写“Starter Pool”“placeholder”之类占位作者/来源
- 链接、作者、标题、发布日期都必须来自真实来源

如果候选池里有假条目，直接丢弃，不要修辞性掩盖。

### 2. 最终精读必须是 LLM 读全文后的结果

不要把规则抽取结果当成正式精读。

可以使用规则做：

- 初筛
- 方向分类
- 候选排序
- 全文结构定位

但**正式日报里的单篇精读**必须由当前 Codex / Claude / LLM 在读过全文解析结果后生成。

### 3. 全文优先用 MinerU

首选：

- `MinerU`

回退：

- 无回退，拿不到可靠 MinerU 全文就不要正式评分

如果拿不到足够可靠的全文，不要正式评分。

### 4. 飞书配置优先读仓库内 `.env.local`

skill / runner 启动时会优先读取仓库根目录的：

- `.env.local`
- `.env`

典型配置：

```bash
FEISHU_WIKI_NODE=your_wiki_node_token
FEISHU_DOC=
FEISHU_TITLE_PREFIX="AI4S 论文速递"
FEISHU_INSERT_MINERU_IMAGES=1
FEISHU_IMAGE_LIMIT_PER_PAPER=2
FEISHU_IMAGE_MIN_BYTES=50000
```

规则：

- `FEISHU_DOC` 存在时：覆盖更新已有文档
- 否则如果有 `FEISHU_WIKI_NODE`：新建到对应知识库节点
- 图片插入默认开启，发布后自动把 MinerU 里挑出的关键图补到对应论文标题后

## 推荐工作流

### 第一步：筛候选

用 helper script：

```bash
python .codex/skills/ai4s-paper-daily/scripts/ai4s_paper_daily.py \
  --date today \
  --output-root outputs/daily-runs \
  --history-pool data/history_pool.json \
  --extract-only \
  --fulltext-backend mineru
```

这一步会生成：

- `selected.json`
- `extraction_manifest.json`
- `cache/fulltexts/`
- `cache/fulltexts/mineru/...`

其中 `extraction_manifest.json` 是后续精读的主入口。

### 第二步：MinerU 全文解析

如果 `extraction_manifest.json` 里某篇论文的：

- `fulltext_backend == "mineru"`
- 且 `markdown_path` 非空

则优先读取：

- `markdown_path`
- 同目录下的 `*_content_list*.json`
- 同目录下的图片资源（若有）

如果 MinerU 没成功：

- 可以看 `pdf_path` 做人工核查
- 但不要正式评分，不要走低质量自动 fallback

### 第三步：LLM 精读（核心）

对每篇最终入选论文，当前模型必须读：

1. 标题 / 作者 / venue / 日期
2. MinerU 解析出的 Markdown
3. 必要时结合内容 JSON / 图片

然后自己写：

```md
## [序号] 论文标题

| 字段 | 内容 |
| --- | --- |
| 来源类型 | 当天新论文 / 历史优质论文 |
| Source / Venue | ... |
| 方向 | ... |
| 方法标签 | ... |
| 作者 | ... |
| 发布日期 | ... |
| 论文链接 | ... |
| PDF 链接 | ... |
| 代码链接 | ... |
| Demo 链接 | ... |
| 全文解析 | mineru |

### 📌 简介
2-4 句话，讲清：
- 任务是什么
- 方法主线是什么
- 这篇为什么值得进日报

### ☠️ 毒舌点评
必须回答：
- 是真创新，还是换皮
- 方法有没有打到痛点
- 实验到底站不站得住
- 值不值得你继续细读

### 🔧 技术方案

**方法主线**
- 整体框架
- 关键模块
- 输入 / 输出 / 监督对象

**核心创新**
- 相比已有方法到底新在哪
- 解决了什么老方法做不好的问题
- 哪些点可能只是 paper framing，不一定是真创新

**训练策略**
- 预训练 / 微调 / post-training / 多阶段训练
- loss / objective
- 数据处理 / augment / negative sampling / curriculum / alignment

### 📊 实验结果

**实验拆解**
- 数据集 / benchmark
- baseline
- 主指标
- ablation
- 泛化 / zero-shot / transfer（如有）
- 开源情况

### ⭐ 评分: X/10
理由：创新性 / 实验可信度 / 对你当前研究的相关性 / 复现价值
```

注意：这里的内容必须是**你读完全文后写的自然语言总结**，不是把规则命中的句子硬拼起来。

### 第四步：每篇写临时稿，防止中断

按 speech workflow 做断点保存：

- 路径：`/tmp/ai4s_papers_YYYYMMDD/<序号>_<paper_id>.md`

每完成一篇就落盘，不要等全部读完再一起写。

### 第五步：生成飞书日报

先创建/更新飞书文档：

```bash
lark-cli docs +create \
  --title "AI4S 论文速递 YYYY-MM-DD" \
  --markdown @outputs/daily-runs/.../report.md \
  --wiki-node "$FEISHU_WIKI_NODE"
```

或者更新已有文档：

```bash
lark-cli docs +update \
  --doc "$FEISHU_DOC" \
  --mode overwrite \
  --markdown @outputs/daily-runs/.../report.md
```

### 第六步：插入 MinerU 图片（可选但推荐）

如果 MinerU 产出了图片资源，可以把每篇最关键的 1~3 张图插到文档里：

```bash
lark-cli docs +media-insert \
  --doc "$DOC_URL_OR_TOKEN" \
  --file path/to/figure.png \
  --caption "Figure: 方法总览 / 核心实验图" \
  --selection-with-ellipsis "[论文标题]"
```

或直接追加到文档末尾。

优先插入：

- 方法总览图
- 主结果图 / 表
- 架构图

不要把所有图都塞进去。

当前 runner 已支持自动插图：

- 发布成功后会按文件大小优先选图
- 默认每篇最多插 `2` 张
- 插入位置是对应论文标题后
- 结果会写回 `publish.json`

## Helper 文件

- `.codex/skills/ai4s-paper-daily/scripts/ai4s_paper_daily.py`
  - 候选筛选
  - 全文下载
  - MinerU 解析
  - `extraction_manifest.json` 输出
- `data/history_pool.json`
  - 历史优质论文池，必须全是真实论文

## 验收标准

完成一次 skill run 后，应该满足：

1. 没有虚构论文
2. 有 `selected.json`
3. 有 `extraction_manifest.json`
4. 单篇精读是 LLM 读全文后写的，不是规则拼句子
5. 飞书文档能创建/更新
6. 若 MinerU 有图片，至少支持自动或手动插图到飞书
