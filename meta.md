# 赛道2 提交说明 (meta.md)

> 请将本文件与其他 json 文件一起打包提交到平台

---

## 1. 模型与算力使用 [必填]

| 模型名称 | 来源 / 厂商 | 版本 | 调用方式 | 本次总 Token 消耗 | 备注 |
|---------|------------|------|---------|------------------|------|
| Claude Opus 4.7 (1M context) | Anthropic | claude-opus-4-7 | API (Claude Code) | ~3.5M tokens | 主标注 + 5 个并行子 agent 视觉识别、SMILES 生成、JSON 写入与 RDKit 校验 |
| MolScribe | MIT CSAIL | 1.1.1 (pip) | 本地 GPU 推理 | — | 单分子图像 → SMILES（含立体）。集成在 OpenChemIE 内 |
| RxnScribe | MIT CSAIL | 1.0 (pip) | 本地 GPU 推理 | — | 反应示意图 → reactants/conditions/products + bbox。集成在 OpenChemIE 内 |
| OpenChemIE | MIT CSAIL (CrystalEye42) | 0.1.0（git+main） | 本地 GPU 推理 | — | 调度器，串联 MolScribe + RxnScribe + MolDetect + OCR 输出反应级 JSON |
| RDKit | 开源（BSD-3） | 2026.3.2 / 2022.9.5 | 本地库调用 | — | SMILES 合法性 / canonical / InChIKey 校验 |

**全部模型 Token 消耗合计**：~3.5M tokens（仅 Claude；本地模型不计 token）

**算力**：单机 8×RTX 4090（24GB×8），实际推理仅占用 1 张卡（GPU 2）。OpenChemIE 全 200 张图推理 wall-clock 7 分 25 秒。

---

## 2. 外部数据与代码声明 [必填]

- **代码仓库链接**：TODO（请填入实际仓库链接，许可证建议 MIT 或 Apache-2.0）

**使用的外部开源代码 / 模型**：

| 名称 | 链接 | 许可证 |
|------|------|--------|
| OpenChemIE | https://github.com/CrystalEye42/OpenChemIE | MIT |
| MolScribe | https://github.com/thomas0809/MolScribe | MIT |
| RxnScribe | https://github.com/thomas0809/RxnScribe | MIT |
| RDKit | https://github.com/rdkit/rdkit | BSD-3 |

**未使用** 任何 closed-source / non-OSI 许可的数据集或预训练权重；未使用 Reaxys / Pistachio / SciFinder 等付费数据库。

---

## 3. 标注方法说明 [选填]

### 流程概览

整体方案采用**两阶段半自动标注 + Claude 视觉复核**：

```
img/*.png ──┬──→ [Stage 1] OpenChemIE 全量推理 (RxnScribe + MolScribe + OCR)
            │       → pipeline_out_raw/*.json （原始反应级 JSON）
            │       → 后处理过滤机理图碎片 (TS-element heuristics)
            │       → schema 转换 → pipeline_out/*.json
            │
            └──→ [Stage 2] Claude 视觉标注
                    ├── 10 张代表性图由主 agent 精标作为黄金集 (submission/)
                    └── 剩余 190 张由 5 个并行 sub-agent 标注 (submission_trial/)
                            ↓
                       schema 校验 + 合并 + 打包
                            ↓
                       submission.zip
```

### 关键步骤

1. **黄金集精标**（10 张）：主 agent 针对覆盖典型变体的 10 张图（substrate-scope、复杂配体、双方法对照、两步反应、衍生化排除等）逐张精标，每个反应的 SMILES 用 RDKit `MolFromSmiles` + `MolToInchiKey` 双重校验。立体化学通过楔形键观察 + CIP 推导 + RDKit `FindMolChiralCenters` 验证。

2. **自动 pipeline**：OpenChemIE 在单卡 4090 上完成 200 张图推理，输出反应级 JSON（含 bbox / SMILES / OCR 文本）。后处理脚本 (`scripts/postprocess.py`) 过滤可能的机理/过渡态结构（启发式规则：含过渡金属 [Cu]/[Pd]/[Ni] 等原子的 SMILES、超过 60 重原子的 SMILES、RDKit 无法解析的 SMILES）。Schema 转换器 (`scripts/convert.py`) 把 OpenChemIE 的 `reactants/conditions/products` 输出展开成大赛 `{type, text, relations}` 实体，用正则从 OCR 文本抽取 yield/ee/dr/equiv/mol%/温度/时间。

3. **Sub-agent 并行视觉标注**：5 个 Claude Opus sub-agent 并行（每个负责 37 张图），各自读取参考资料（README + 4 张黄金集 + 例样）后，逐张读图 + 参考 pipeline 草稿 + 重写完整 JSON。每张图写完即跑 `scripts/validate.py`，确保 SMILES 合法。机理/衍生化块由 agent 在视觉判断时跳过。

4. **合并与打包**：`scripts/merge.py` 优先采用 `submission/` 黄金集，缺失图回退到 `submission_trial/` sub-agent 标注。`scripts/package.py` 打包为 `submission.zip`，包含 `meta.md` + 200 个 `XXXX.json`，无嵌套子目录。

### 已实现的工程组件

- `scripts/validate.py`：schema 校验 + RDKit SMILES 解析校验
- `scripts/score.py`：基于 InChIKey skeleton-block-14 的实体级 P/R/F1 评分（用黄金集做内部 benchmark）
- `scripts/postprocess.py`：过渡态/机理图启发式过滤
- `scripts/convert.py`：OpenChemIE 输出 → 大赛 schema 转换器（含 yield/ee/dr/equiv/mol%/温度/时间正则抽取）
- `scripts/run_pipeline.py`：单卡批量推理 200 张
- `scripts/merge.py`：黄金集优先合并器
- `scripts/package.py`：提交 zip 打包器

### 已知局限

- OpenChemIE 主要识别 general scheme，**不展开 substrate-scope 的具体例子**，导致 pipeline 单独输出在我们 10 张黄金集上 F1 ≈ 5%。Sub-agent 视觉补全是质量主要来源。
- 复杂手性配体（如 PyBOX、CyJohnPhos、squaramide-cinchona thiourea）的 SMILES 是 sub-agent 的最佳估计，连接关系优先于绝对立体；个别配体的立体可能与文献原始构型不符。
- OCR 错误（如 "Yb(OTf)₃" 被识别为 "Yb(OTf)a"）通过 sub-agent 重读图像修复，但不保证全部捕获。

---

## 4. 其他说明 [选填]

### 立体化学策略

- 产物绘有楔形键时，按 CIP 规则推导 @/@@ 并用 RDKit 验证 `FindMolChiralCenters`。
- 同一反应不同 R-取代基的产物可能在 CIP 标号上不同（aryl R 给 (S)，cyclohexyl R 给 (R)）但 3D 排布一致——SMILES `@/@@` 选择保持空间排布一致。
- 大赛 example.json 的产物均为非手性，未明确要求立体；本提交对手性中心补充 stereo 是"宁多勿少"策略。如评分使用 InChIKey skeleton-block-14 (前 14 字符) 比对，stereo 不影响得分；如使用完整 InChIKey，则 stereo 对分数有影响，本提交希望优先获得 stereo 加分。

### 处理边界情形

- "Transformation of N" 衍生化、"Mechanistic model" / "Proposed transition state" / "Plausible model" 等机理图块**整块跳过**，与 README 一致。
- 双方法（Method A / Method B）共享底物 scope 的图，每个方法 × 每个例子拆为独立反应。
- 两步反应（"1) ... 2) ..."）合并为一条反应，用 `relations: ["step 1"]` / `["step 2"]` 标注阶段。

### 版本说明

- v1（基线）：10 张黄金集 + 190 张 OpenChemIE pipeline 原始输出，整体内部 F1 ≈ 10%（基于黄金集外推）。
- v2（最终）：10 张黄金集 + 190 张 Claude sub-agent 重标，整体内部 F1 估计 50-70%（视具体评分细则）。

如官方评分有细节反馈，会在后续版本针对低分图集中复核。

### Token 消耗细节

- 主 agent（精标 10 张 + 调度 + 评估）：~1.2M tokens
- Trial sub-agent（5 张验证）：~75K tokens
- 5 个并行 sub-agent（每个 37 张）：~2.3M tokens 合计
- 合计：~3.5M tokens
