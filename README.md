# ClaimAudit · 验货员

[![ci](https://github.com/ironmanstar-lab/claimaudit/actions/workflows/ci.yml/badge.svg)](https://github.com/ironmanstar-lab/claimaudit/actions/workflows/ci.yml)

**宣称 vs 证据。** 给它一个「开源神器 / AI 教程 / 致富方法」的链接，它给你一份能复核的尽调报告：哪些话有证据、哪些只是气氛、30 分钟内你自己该怎么验。

```bash
claimaudit https://github.com/owner/repo
```

```
结论：B（76.8 / 100）· 有真东西但掺水：先做自检清单，再决定要不要投入
首要红旗：评分封顶：共 3 次提交、建库 77 天：更像一次性发布，不是持续演进的代码库
```

> 真实样例：[`examples/report-dshquant.md`](examples/report-dshquant.md)（一个上过抖音热门的量化项目）、
> [`examples/report-article.md`](examples/report-article.md)（一篇媒体报道）、
> [`examples/report-video-no-transcript.md`](examples/report-video-no-transcript.md)（只有视频链接时它会拒绝打分）。

---

## 为什么不是又一个「仓库摘要器」

GitHub 上不缺读懂代码的工具，缺的是**核对宣传**的工具。两者的差别：

| | 仓库摘要 / 代码审计 | ClaimAudit |
|---|---|---|
| 回答的问题 | 这个仓库写了什么 | **它说的和它做的是不是一回事** |
| 输入 | 仓库 | 仓库 / 文章 / 视频 / 任意文案 |
| 输出 | 结构说明 | 宣称-证据对照表 + 评分 + 红旗 + 自检清单 |
| 判定 | 主观描述 | 18 条固定检查，同输入同输出 |
| 失败模式 | 说得漂亮但没用 | **证据不足时拒绝定级**，而不是硬给个分 |

它的立场很窄也很硬：**不判断真假，只判断「有没有可核的证据」，并告诉你怎么去核。**

## 60 秒上手

```bash
git clone https://github.com/ironmanstar-lab/claimaudit
cd claimaudit
python -m claimaudit.cli https://github.com/owner/repo     # 仓库
python -m claimaudit.cli https://example.com/sales-page    # 文章/落地页
python -m claimaudit.cli https://v.douyin.com/xxxx/ --transcript 文案.txt   # 视频 + 字幕
python -m claimaudit.cli README.md                         # 本地文案
python -m claimaudit.cli <target> --html --out r.html      # 单文件 HTML，直接发人
```

零依赖，Python 3.9+ 即可，不需要 API Key、不需要 Node、不需要装包。

想当命令用：

```bash
pip install -e .
claimaudit https://github.com/owner/repo --json > report.json
```

## 它到底查什么

六维、18 条检查（细则见 [`docs/rubric.md`](docs/rubric.md)）：

| 维度 | 权重 | 举例 |
|---|---:|---|
| 可验证性 | 25 | 宣称里有多少条带数字口径；有没有外部可核链接；有没有方法论 |
| 证据密度 | 20 | 测试、CI、可复现的 demo 数据、独立文档 |
| 宣称一致 | 20 | README 里点名的模块，文件树里真的有吗；说开源有没有 LICENSE；说一键装，依赖几个 |
| 维护可信 | 15 | 最近提交、提交节奏、贡献者数量（bus factor） |
| 风险敞口 | 10 | 引流钩子（加群/网盘/私域）、提交的 exe、免责声明 |
| 上手成本 | 10 | 依赖规模、是否需要自备付费数据或 Key、有没有三步能跑通的说明 |

还有三条**封顶规则**，因为加权求和会被漂亮的文档骗过去：

- 提交 ≤ 5 次且建库 > 30 天 → **最高 B**（一次性发布，不是活的代码库）
- 交付物含二进制 / `node_modules` → **最高 C**
- 宣称开源却没有 LICENSE、或收益宣称却没有免责声明 → **最高 C**

以及一条**拒答规则**：视频没有字幕、正文不足 200 字时，它输出「未定级」并把缺口列出来 —— 硬给一个分数才是耍流氓。

## 给 agent 用

ClaimAudit 本身是 CLI，任何 agent 都能当工具调：

```bash
claimaudit <target> --json          # 稳定 schema，含每项检查的证据
claimaudit <target> --fail-under 70 # 分数不达标返回 4，可以卡 CI 依赖
```

仓库自带 [`SKILL.md`](SKILL.md)：把「先跑工具拿事实，再让模型解释」的顺序写死，避免模型先下结论再找理由。

## 输出长什么样

`--json` 给出 `score / grade / dims / checks[] / redflags / gaps / checklist / claims[]`，每一项都带 `evidence` 字符串 —— 分数永远能追到一句可核对的话。

`--out report.md` 写 Markdown：评分卡、宣称 vs 证据表、红旗、证据缺口、30 分钟自检清单、原始事实。

`--html`（或 `--out report.html`）出自包含单文件 HTML：样式内联、无脚本、无外链，可以直接发给不装 Python 的人看。

## 怎么保证「改了是变好，不是变样」

迭代这种规则系统，最大的敌人是「改完感觉更准了」。所以仓库里放了一个**黄金集**：

```bash
python bench/run.py
```

```
样本                 等级     分数      期望       结果
good_lib           S      89.1    S/A       PASS
dump_repo          B      64.5    B         PASS
abandoned          C      42.8    C/D       PASS
no_license_claim   C      66.1    C         PASS
article_good       A      77.9    A/B       PASS
article_hype       D      35.9    C/D       PASS
video_no_transcript —      42.9    —         PASS
```

七个样本各自带期望等级（`_expect`），`tests/test_bench.py` 把这套基准接进 CI：
**谁把规则改坏了，CI 直接红。** 样本都是合成的，但事实结构取自真实见过的项目，
校准的是规则之间的相对关系，不是给某个具体仓库打分。

## 边界（请先读这段）

- **它不判断真假。** 它判断「有没有证据、证据够不够」。一个真项目也可能因为文档差拿低分。
- **规则是启发式的。** 目的不是判决，是把讨论对齐到具体事实。不同意某条权重，改 `claimaudit/rubric.py` 里的一行数字即可。
- **抓取能力有限。** 需要登录的页面、纯 JS 渲染的页面、反爬站点，取不到就是取不到 —— 报告会写「未取到」，不会替你猜。
- **GitHub 匿名配额 60 次/小时。** 批量用请设 `CLAIMAUDIT_TOKEN`。
- 视频没有公开字幕接口。想核口播，自己准备文案（`--transcript`）。

**它明确不能做的四件事**（写在这里，免得你误会）：

- **不判断真假**，只判断「有没有可核的证据、够不够」；
- **不审代码逻辑**，只核对「宣称的结构」和「实际的结构」是否一致；
- **不突破登录墙**，抓不到就写「未取到」，不会编；
- **不替你做决定**，分数只是把讨论对齐到具体事实。

## 开发

```bash
python -m unittest discover -s tests -t .   # 44 个用例，不联网
python bench/run.py                         # 黄金集：7 个样本对不对得上
claimaudit --offline claimaudit/fixtures/hype_case.json   # 用快照看低分长什么样
```

结构：

```
claimaudit/
  http.py        缓存 + 重试 + 限流提示（stdlib urllib）
  sources/       github / web / video / textfile 四个适配器
  claims.py      中文·英文卖点词表 + 行级上下文抽取
  rubric.py      18 条检查 + 三条封顶 + 拒答
  report.py      Markdown / JSON 渲染
  cli.py         命令行与退出码
```

MIT. 拿去改，改了欢迎 PR。

---

**English**: ClaimAudit audits *claims*, not vibes. Point it at a repo, an article, or a video share link; it collects machine-checkable facts (commit cadence, file tree vs. advertised modules, LICENSE, tests, promo hooks), scores them against an 18-check rubric, and prints a claim-vs-evidence report plus a 30-minute verification checklist. Zero dependencies, deterministic output, and it refuses to grade when the evidence isn't there.
