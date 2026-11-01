# 代码导读 · 目录

按这个顺序读，大约 40 分钟能把这 2300 行读完。

| # | 文档 | 讲什么 | 对应的代码 |
|---|---|---|---|
| 00 | [总览](00-总览.md) | 目录职责、数据流、两个核心契约、阅读顺序 | 全部 |
| 01 | [基础设施](01-基础设施.md) | 时间工具、网络层（缓存/重试/错误分类/SSL 降级） | `util.py` `http.py` |
| 02 | [四个适配器](02-四个适配器.md) | 仓库/网页/视频/本地文案怎么变成 `facts` | `sources/*` |
| 03 | [宣称抽取](03-宣称抽取.md) | 八类词表、四道过滤器、为什么用正则不用 LLM | `claims.py` |
| 04 | [评分引擎](04-评分引擎.md) | 18 项检查、三条封顶、拒答、加权与归一 | `rubric.py` |
| 05 | [渲染与 CLI](05-渲染与CLI.md) | 三种输出、目标分发、退出码 | `report.py` `cli.py` |
| 06 | [基准与测试](06-基准与测试.md) | 黄金集怎么设计、单测怎么分层 | `bench/` `tests/` |
| 07 | [设计决策](07-设计决策.md) | 为什么这么写、踩过的坑、扩展指南 | 全部 |

---

## 只想快速上手的话

```bash
# 1) 看它怎么判断一个仓库（不联网，用快照）
python -m claimaudit.cli --offline claimaudit/fixtures/hype_case.json

# 2) 跑一遍黄金集，理解规则之间的相对关系
python bench/run.py

# 3) 真跑一个
python -m claimaudit.cli https://github.com/yuanwang589-dev/deepseek-harness-quant

# 4) 看机器怎么读结果
python -m claimaudit.cli <target> --json | head -50
```

---

## 改代码前请记住三条纪律

1. **事实与判断分离**：`sources/` 只取数，`rubric.py` 只判断；
2. **判断可复现**：任何检查都不该依赖随机、网络或当前时间以外的东西；
3. **不确定就说不确定**：`None`（不适用）≠ `0`（做得很差），拒答优先于瞎给分。

改完必跑：

```bash
python -m unittest discover -s tests -t .
python bench/run.py
```
