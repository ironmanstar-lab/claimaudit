# 05 · 输出与入口：report.py 与 cli.py

---

# 一、`report.py`（349 行）— 同一个结果，三种表达

| 函数 | 给谁看 | 特点 |
|---|---|---|
| `render()` | 人，终端/Markdown | 六节结构，表格化 |
| `render_json()` | agent / 脚本 | 稳定 schema，含每项检查的证据 |
| `render_html()` | 人，分享 | 自包含单文件，无外链无脚本 |

---

## 1. 宣称 → 证据的映射（第 12–62 行）

报告里那张「它说 / 我们核到 / 判定」表，证据是从**检查结果**里借来的。

```python
CLAIM_KIND_TO_CHECK = {
    "money": "disclosure",        # 收益宣称 → 看有没有免责
    "absolute": "claim_numbers",  # 绝对化   → 看整体可核比例
    "quantity": "module_claims",  # 数量宣称 → 看模块对不对得上
    "effortless": "install_claim",
    "free_open": "license_claim",
    "time": "quickstart",
    "authority": "external_refs",
    "social": "external_refs",
}
```

`_check_id_for()`（第 45 行）有个分支：**非仓库目标**里，
`free_open` / `effortless` 没有 LICENSE、依赖可言，改指向 `external_refs`。
否则会出现“未取得可核证据”的空洞行（0.1.0 的 bug）。

`_mark()`（第 26 行）把 pct 变成三档符号：
≥0.75 ✅ / ≥0.4 ⚠️ / 否则 ❌。**不显示具体数字**——读者要的是结论，不是 0.63。

## 2. `render()` · 第 77 行 — 六节结构

```
# 验货报告 · <目标>
> 结论：B（76.8/100）· 有真东西但掺水
> 首要红旗：…
## 一、评分卡        ← 六维 + 进度条
## 二、宣称 vs 证据   ← 最多 8 行，每类最多 2 条
## 三、红旗
## 四、证据缺口
## 五、30 分钟自检清单
## 六、采集到的事实   ← 仓库/网页的关键字段
```

几个刻意的取舍：

- **红旗放第三条**，不是最后——读者最先想知道“哪里有问题”；
- **缺口（gaps）单列一节**：分数是判断，缺口是边界，两件事；
- **清单给命令**：GitHub 目标会附一条 `claimaudit <url> --json | jq ...`，
  让读者能自己复核，而不是信我；
- **`_pick_claims(limit=8, per_kind=2)`**：同一个毛病说两遍就够，多了像凑数。

`_bar()`（第 35 行）用 `█░` 画 10 格进度条。终端里比百分比直观，Markdown 里也不难看。

## 3. `render_json()` · 第 229 行

就是 `json.dumps(audit.as_dict())`。schema 见 `00-总览.md`。
**这是给 agent 的接口**：字段名一旦发布就不要改，改了算 breaking change。

## 4. `render_html()` · 第 263 行

**为什么要有**：`--json` 给机器，`render()` 给终端，但你想把报告发给一个不装 Python 的人时，
两者都不合适。HTML 单文件是唯一解。

三条硬约束：

1. **样式内联**（`HTML_CSS`，第 237 行）——不引外部 CSS，断网也能看；
2. **零脚本**——避免在别人的浏览器里执行任何东西，也不会被当成钓鱼页；
3. **全部转义**（`_e()`，第 233 行）——README 里可能有人写 `<script>`，必须转义。

`test_html_escapes_user_content` 就在守这条：往 description 里塞 `<script>alert(1)</script>`，
渲染结果里不能出现它。

---

# 二、`cli.py`（143 行）— 入口与分发

## 1. `build_parser()` · 第 25 行

| 参数 | 作用 |
|---|---|
| `target` | 仓库 / 网页 / 视频 / 本地文件 |
| `--transcript PATH` | 视频字幕或口播文案 |
| `--json` / `--html` / `-o PATH` | 输出格式（`-o *.html` 会自动切 HTML） |
| `--token` | GitHub token（也读 `CLAIMAUDIT_TOKEN` / `GITHUB_TOKEN`） |
| `--deep` | 多花 1–2 个请求核 Release |
| `--offline FIXTURE.json` | 用快照打分，不联网（演示与测试） |
| `--no-cache` | 绕开本地缓存 |
| `--fail-under N` | 低于 N 返回退出码 4（CI 门禁） |

## 2. `load_payload()` · 第 49 行 — 判断“这是什么”

**顺序很重要**：

```python
1. --offline           → 直接读 JSON 快照
2. 本地文件存在        → textfile
3. 像 GitHub slug      → github
4. 像本地路径但不存在  → 报错（别当成仓库名去请求）
5. 视频链接            → video
6. http(s) 链接        → web
7. 其它                → 用法错误
```

为什么 2 在 3 前面：`docs/report.md` 这种字符串既像文件路径又像 `owner/repo`。
先看磁盘，再看网络，才不会把一个本地文件当成仓库名去查。

为什么 4 存在：用户把路径打错时，报“本地文件不存在”比报“仓库 404”有用得多。

## 3. `run()` · 第 90 行 — 主控

```python
try:    payload = load_payload(args)
except NotFound   → 打印 + 返回 2
except RateLimited→ 打印（含“N 分钟后恢复”）+ 返回 2
except FetchError/OSError → 返回 2
except ValueError/JSONDecodeError → 返回 3

ctx   = rubric.build_context(payload)
audit = rubric.score(ctx)
body  = json / html / markdown
写文件 or 打印
if --fail-under and score < N: 返回 4
```

## 4. 退出码约定（给 CI 用）

| 码 | 含义 | 典型场景 |
|---:|---|---|
| 0 | 成功 | — |
| 2 | 取数失败 | 网络断、仓库不存在、配额用尽 |
| 3 | 用法错误 | 没给目标、文件不存在、fixture 结构不对 |
| 4 | 低于门槛 | `--fail-under 70` 而实际 62 |
| 130 | 用户中断（Ctrl+C） | — |

`--fail-under` 是最实用的隐藏功能：可以拿它卡依赖。
比如团队规定“不许引入 C 级项目”，就在 CI 里对候选仓库跑一遍。

---

## 三、三处容易改错的地方

1. **`print(body)` vs 写文件**：`--json` 时不要加任何额外输出，
   否则管道里的 `jq` 会解析失败（现在的实现在 `--out` 时才打印提示行）；
2. **编码**：`http.ensure_utf8_stdout()` 必须在任何打印之前调用；
3. **HTML 换行**：`render_html` 不加尾随 `\n` 也没关系，但 `-o` 分支统一加一个，
   避免某些编辑器把整份文件当一行。
