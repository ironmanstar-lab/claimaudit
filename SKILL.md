---
name: claim-audit
description: Audit hype-laden tech content (GitHub repos, articles, video share links) by running the claimaudit CLI to collect machine-checkable evidence, then explaining the claim-vs-evidence report. Use when the user asks 这个项目靠谱吗 / 值不值得上手 / 这是不是割韭菜 / 帮我看看这个开源项目, or shares a link to an "AI 神器" before deciding to invest time or money.
---

# 验货（ClaimAudit）

当一个链接带着「开源 / 一键 / 免费 / 月入 / 全网首发」进来时，**先拿事实，再给判断**。顺序不能反。

## 何时用

- 用户丢来一个 GitHub 仓库、公众号文章、抖音/B站/小红书分享链接，问「靠谱吗 / 值不值 / 能不能用」。
- 用户准备把时间或钱投到一个宣称有奇效的东西上（课程、社群、量化系统、AI 工具）。
- 用户想让你评价一个项目的工程完成度，而不只是它写了什么。

## 怎么做

1. **跑工具，别先下结论。**

   ```bash
   claimaudit <link> --json
   ```

   链接是视频就先要文案，再跑：

   ```bash
   claimaudit <video-link> --transcript 文案.txt
   ```

2. **读三样东西**（其它都可以不看）：
   - `grade` / `score`：定级（`—` 表示证据不足，不许硬评）。
   - `redflags`：命中即说，按顺序说。
   - `gaps`：它没被核实的部分 —— 这往往比分数更重要。

3. **翻译成人话**，按这个结构回答：
   - 一句话结论（等级 + 为什么）。
   - 它说的 vs 我核到的（最多 3 条，挑 `pct` 最低的）。
   - 红旗（有就列，没有就说没有）。
   - 30 分钟自检清单（用 `checklist`，按优先级）。
   - 我的建议：能当依赖用 / 值得投入 / 先自检 / 只当素材 / 别碰。

4. **需要更细的核对时**，用 `--json` 里的 `checks[].evidence` 去回答，不要自己编数字；取不到就说取不到。

## 硬约束

- **不许把分数当判决。** 报告是「对齐讨论」的工具，措辞用「证据够不够」，不用「真假」。
- **不许跳过工具直接评价。** 你的印象不是证据；工具没跑就别给等级。
- **不许在 `grade == "—"` 时编结论。** 直接说缺什么（字幕、原文、代码），并给出补齐的命令。
- 引用仓库事实时只引用 `facts` 里有的字段；`--deep` 才会核 Release，不要假装核过。
- 用户如果只要一个态度，也要先给「依据 → 结论」，不要只给结论。

## 输出模板

```
结论：B（76.8/100）—— 有真东西，但停在发布当天
依据：305 star / 3 次提交 / 建库 77 天后没再推代码；README 点名的 8 个模块文件树里都有
红旗：评分封顶（一次性发布）
建议：当教材读，不要当仓位
下一步：<checklist 前 3 条>
```
