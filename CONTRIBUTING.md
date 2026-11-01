# 贡献指南

先说结论：**这个仓库接受「能让黄金集更准」的改动，不接受「让某个项目分数变好看」的改动。**

---

## 三条不能破的纪律

1. **事实与判断分离** —— `sources/` 只取数，`rubric.py` 只判断。别在取数层写评分逻辑。
2. **判断必须可复现** —— 不许引入随机、当前网络状态、或“看心情”的分支。
3. **不确定就说不确定** —— `None`（不适用）≠ `0`（做得很差）；拒答优先于瞎给分。

---

## 改规则的流程（重要）

任何对 `rubric.py` 的改动（权重、阈值、封顶、新增检查），都必须按这个顺序：

### 1. 先写样本，再改代码

在 `bench/golden/` 新增一个样本，`_expect` 写清楚**你期望什么等级、为什么**：

```json
{
  "_expect": {"grades": ["B"], "note": "文档漂亮但一次性发布，封顶应生效"}
}
```

日期用相对占位符 `@-80d`，不要写死（样本会老化）。

### 2. 跑黄金集，贴前后对比

```bash
python bench/run.py
```

PR 描述里必须有这张表：

| 样本 | 改前 | 改后 | 期望 | 结论 |
|---|---|---|---:|---|
| `dump_repo` | B 64.5 | B 62.1 | B | 仍合规 |
| `good_lib` | S 89.1 | S 89.1 | S/A | 未受影响 |

**只要有一个样本从 PASS 变 FAIL，这个 PR 就不成立**——除非你在 PR 里论证“那个期望本身错了”，
并且同步改 `_expect` + 说明理由。

### 3. 改 `RUBRIC_VERSION`

```python
# claimaudit/rubric.py
RUBRIC_VERSION = "0.3"   # 0.2 → 0.3
```

报告里会打印它，读者才知道“这两份报告能不能比”。

### 4. 补测试

- 新检查 → 至少一条 `test_rubric.py` 用例（含“不适用时返回 None”）；
- 新输出 → `test_report.py` 里的渲染断言；
- 修 bug → **先写能复现 bug 的测试**，再修。

---

## 会被拒绝的 PR

| 类型 | 为什么 |
|---|---|
| “把我的项目分数改高一点” | 这是本仓库存在的理由的反面 |
| 删除拒答逻辑 | 拒答是最难写对、也最不该妥协的一条 |
| 引入第三方依赖 | 零依赖是硬约束（见 README 的「为什么」） |
| 让 `sources` 直接调用 `rubric` | 破坏分层 |
| 改权重但不带样本 | 无法判断是变好还是变样 |
| 大范围重构 + 功能混在一个 PR | 分开提，好审也好回滚 |

---

## 加一条检查的标准动作

```python
# 1) 在 claimaudit/rubric.py 里写函数
def _has_changelog(ctx, now):
    paths = (ctx["facts"].get("tree") or {}).get("paths") or []
    if not paths:
        return None                      # 不适用 → 直接跳过
    ok = any(p.lower().startswith("changelog") for p in paths)
    return (
        1.0 if ok else 0.2,              # pct
        "有 CHANGELOG" if ok else "没有 CHANGELOG",   # evidence：必须说人话
        None,                            # redflag：真有问题才填
        None if ok else "让作者补一个变更记录",        # action：进自检清单
    )

# 2) 在 CHECKS 表里注册
("has_changelog", "证据密度", 3.0, _has_changelog),
```

**先问自己：这条检查能为什么红旗提供证据？** 给不出答案就先别加。

---

## 加一个数据源

1. 新建 `claimaudit/sources/xxx.py`，实现 `probe()`，返回统一结构：

```python
{"source": "xxx", "target": "...", "url": "...", "notes": [...], "facts": {...}}
```

2. 在 `cli.load_payload()` 里加一个分支（注意顺序：本地文件要排在 URL 判断之前）；
3. 不需要碰 `rubric.py`——它只认 `facts` 里有的字段，缺的检查会自动跳过。

---

## 提交信息

```
feat(rubric): 新增 has_changelog 检查
fix(claims): 修掉「收益宣称」被误判为 money
docs: 补「已知误判」清单
```

中文可以，写清楚**改了什么 + 为什么**。只写 “update” 的 PR 会被要求重写。

---

## 本地检查清单

```bash
python -m unittest discover -s tests -t .   # 必须全绿
python bench/run.py                          # 必须 7/7
```

两条都过，再开 PR。
