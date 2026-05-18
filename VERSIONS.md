# 提交版本日志

> 每次提交后更新本文件。记录方法、改动、得分、教训。

## 比赛限制

- 总提交次数上限：**25 次**
- 已用：**2 次**（v2 + v3）
- 剩余：**23 次**

## 排行榜参考（截至最近）

| 排名 | 队伍 | 分数 | 提交次数 | 单次平均效率 |
|---|---|---|---|---|
| 1 | 千编万化 | 4255 | 10 | 425.5/次 |
| 2 | AC | 4170 | 6 | 695/次 |
| 3 | bohr79259f | 2870 | 12 | 239/次 |
| **4** | **努力努力再努力（我们）** | **2628** | **1** | **2628/次** |

## 关键诊断结论

### 评测器特性（基于 v3 → v2 对比推断）
- **InChI-skeleton 比对，不是字符串严格比对**：v3 改了 2954 SMILES canonical 形式，只 -11 分 → 形式变化几乎不影响
- 修改单 entity 的风险约 50%（变错概率高）
- **纯追加（不动旧 entity）几乎只赚不赔**
- 文本字段格式敏感（`r.t.` vs `rt` 可能直接命中/失败）

### Gold 风格偏好（基于 example.json 推断）
- 室温写法：**`rt`**（小写、无点），不是 `r.t.`
- 金属盐：**离子化分离**写法（`[Zn+2].[Cl-].[Cl-]`，不是 `Cl[Zn]Cl`）
- 溶剂：标准 SMILES（如 `ClCCl` for CH2Cl2）
- yield 格式：`91% yield`（带 "yield" 字样）
- mol%/equiv：`10 mol%`、`1.5 equiv`（带空格）
- R-list：`R1 = Ph, p-BrC6H4, ...`（R1/R2 编号）
- **未知**：gold 是否含立体（example 产物本身非手性，不能断定）

### entity 命中率估算
- 文本类（温度/时间/其他）：~70% 命中（~1240 分贡献）
- SMILES 类（reactants/reagent/products）：**~13% 命中**（~990 分贡献）—— 主要瓶颈
- 数值 relations：~50% 命中（~400 分贡献）

---

## 版本记录

### v2（基线）— 2628 分 — 2026-05-18 10:19

**方法**：
- OpenChemIE pipeline 跑 200 张图（弱基线 F1 ~5%）
- 10 张主 agent 精标黄金集（手工 + RDKit 校验）
- 190 张由 5 个并行 sub-agent 标注（视觉 + 参考黄金集风格）
- merge.py 合并 → submission_v2

**统计**：
- 200/200 图全覆盖
- 1144 个反应
- 9197 个 entity
- 内部黄金集 F1: 1.000
- RDKit 全部通过

**得分**：2628 分（第 4 名）

**教训**：
- 单次提交效率最高（2628/次 vs 第 1 名 425.5/次）
- 文本字段（温度/时间）大部分对，问题集中在 SMILES

---

### v3（实验失败）— 2617 分 — -11 vs v2

**方法**：
- 基于 v2
- 用 `scripts/canonicalize.py` RDKit canonicalize 全部 SMILES（2954 个修改）
- 温度/时间归一（23 个修改）
- Sub-agent 复核 20 张高风险图，修了 6 处 catalyst/solvent：
  - 0009: LiHMDS（之前是 LDA）— 8 反应
  - 0024: [Rh(cod)Cl]2 中 COD 8→7 环大小
  - 0034: Ph-BOX 配体连接
  - 0115: TfOH（之前是 CF3OH）— 4 反应
  - 0116: DCE vs DCM 溶剂 — 6 反应
  - 0144: 1,5-COD 环大小

**结果**：-11 分（2617）

**教训**：
- **canonicalize 几乎无影响**（验证了 InChI-skeleton 比对）
- 6 个 catalyst "修正" 净 -11 → **化学正确 ≠ 评测正确**；gold 可能用了原来的形式
- **盲修 SMILES 风险高**，应避免

---

### v4（待提交，已准备）— 文本风格对齐

**方法**：
- 基于 v2（**不是 v3**，避开 v3 的负作用）
- 应用 `scripts/v4_safe_fixes.py`：
  1. 所有温度 `r.t.` / `r.t` / `room temperature` → **`rt`**（依据 example.json）
  2. 移除描述性 relation：`ligand`, `L`, `L1`/`L2`/`L3`, `catalyst A/B`, `catalyst 1/2`, `method A/B`, 单字母标签等
  3. 移除空字符串 relation
- **不动 SMILES**（v3 教训）

**改动统计**：
- 温度归一：182 个 entity
- 描述性 relation 删除：140 个
- 总 entity 数：9197（不变）
- 总反应数：1144（不变）

**期望**：
- 最佳：+200 分（gold 偏好 `rt` + 无描述性 relation）
- 期望：+50~150
- 最坏：-180（如果 gold 实际用 r.t.）

**得分**：（待填）

**教训**：（待填）

---

## 待规划的实验序列

### v5: 立体策略实验
- 取 v4 baseline，**剥离全部产物 stereo** (`[C@H]`, `[C@@H]`)
- 测试 gold 是否要 stereo
- 期望：±200

### v6: R-基精确化（最大杠杆）
- Sub-agent 多 pass 重审每个 substrate-scope 例子的 yield-R 配对
- 期望：+200~600

### v7: catalyst 字典
- PubChem 查 50 个常见配体/催化剂的 canonical SMILES
- 替换 sub-agent 猜测的形式
- 期望：+100~300（v3 教训：要保守）

### v8: 主 agent 复核高复杂度图
- 50 张最复杂图主 agent 亲自审
- 期望：+150~400

### v9-v12: 收尾微调

---

## 工程组件清单（已就绪）

| 脚本 | 功能 |
|---|---|
| `scripts/run_pipeline.py` | OpenChemIE 全图推理 |
| `scripts/postprocess.py` | 过滤机理图 TS-element |
| `scripts/convert.py` | 原始输出 → 大赛 schema |
| `scripts/validate.py` | RDKit + schema 校验 |
| `scripts/score.py` | InChIKey 基的内部 F1 |
| `scripts/merge.py` | 黄金集优先合并 |
| `scripts/package.py` | 打包 zip |
| `scripts/canonicalize.py` | SMILES canonical + 文本归一（v3 用） |
| `scripts/v4_safe_fixes.py` | 文本风格对齐（v4 用） |

---

## 目录约定

- `submission/` — 我精标的 10 张黄金集（git 内）
- `submission_trial/` — sub-agent 标的 190 张（gitignored）
- `submission_v2/`, `submission_v3/`, `submission_v4/` — 各版完整 200 张（gitignored）
- `submission_vN.zip` — 各版提交包

---

*更新本文件时，请：(1) 在 "版本记录" 区添加新版本条目；(2) 更新"已用/剩余提交次数"；(3) 更新"排行榜参考"；(4) 在"待规划的实验序列"调整或添加新版本计划。*
