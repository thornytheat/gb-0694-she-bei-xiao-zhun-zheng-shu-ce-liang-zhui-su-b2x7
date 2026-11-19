# 深度登记 设备校准证书与测量追溯

- 规模：中型
- 使用者与工作流：检验机构质量员，合并仪器使用与校准证书，裁决测量是否在有效可追溯链内。
- 核心规则：证书有效期与量程双约束；参考标准也须在校准时有效，证书撤销向下游传播并检测环。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 证书接收 | 运行证书接收并复核证据 | `POST /api/m1`；`/work/1` | `app/modules/m1_receiving/rules.py` | `tests/test_m1.py` |
| M2 设备别名 | 运行设备别名并复核证据 | `POST /api/m2`；`/work/2` | `app/modules/m2_identity/rules.py` | `tests/test_m2.py` |
| M3 有效区间 | 运行有效区间并复核证据 | `POST /api/m3`；`/work/3` | `app/modules/m3_validity/rules.py` | `tests/test_m3.py` |
| M4 量程匹配 | 运行量程匹配并复核证据 | `POST /api/m4`；`/work/4` | `app/modules/m4_ranges/rules.py` | `tests/test_m4.py` |
| M5 溯源链路 | 运行溯源链路并复核证据 | `POST /api/m5`；`/work/5` | `app/modules/m5_trace/rules.py` | `tests/test_m5.py` |
| M6 测量裁决 | 运行测量裁决并复核证据 | `POST /api/m6`；`/work/6` | `app/modules/m6_verdict/rules.py` | `tests/test_m6.py` |
| M7 撤销复核 | 运行撤销复核并复核证据 | `POST /api/m7`；`/work/7` | `app/modules/m7_revocation/rules.py` | `tests/test_m7.py` |
| M8 符合性声明 | 出具带整链不确定度的符合性声明并追溯来源 | `POST /api/m8`；`/work/8` | `app/modules/m8_declaration/rules.py`、`app/domain.py` | `tests/test_m8.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现会怎样 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-01 | 旧编码证书 | 静默覆盖或误计 | 显式裁决并保留证据 | `app/modules/m1_receiving/rules.py` | `tests/test_m1.py::test_legacy_chinese` |
| TRAP-07 | 空值测量 | 静默覆盖或误计 | 显式裁决并保留证据 | `app/modules/m2_identity/rules.py` | `tests/test_m2.py::test_missing_isolated` |
| TRAP-08 | 设备编码保形 | 静默覆盖或误计 | 显式裁决并保留证据 | `app/modules/m2_identity/rules.py` | `tests/test_m2.py::test_device_code_preserved` |
| TRAP-14 | 定义冲突 | 静默覆盖或误计 | 显式裁决并保留证据 | `app/modules/m2_identity/rules.py` | `tests/test_m2.py::test_conflict_certificate_flag` |
| TRAP-20 | 溯源依赖环 | 静默覆盖或误计 | 显式裁决并保留证据 | `app/modules/m5_trace/rules.py` | `tests/test_m5.py::test_reference_cycle` |
| TRAP-22 | 设备别名 | 静默覆盖或误计 | 显式裁决并保留证据 | `app/modules/m2_identity/rules.py` | `tests/test_m2.py::test_alias_order_independent` |
| TRAP-23 | 失效日边界 | 静默覆盖或误计 | 显式裁决并保留证据 | `app/modules/m3_validity/rules.py` | `tests/test_m3.py::test_expiry_endpoint` |
| TRAP-25 | 多证书重叠 | 静默覆盖或误计 | 显式裁决并保留证据 | `app/modules/m3_validity/rules.py` | `tests/test_m3.py::test_overlapping_certificates` |
| TRAP-30 | 不确定度缺失被当零 | 缺失值静默按0合成，出具虚假“符合” | 缺失沿整链传播为“无法判定”，声明仍编号登记待重算 | `app/modules/m8_declaration/rules.py` | `tests/test_m8.py::test_missing_uncertainty_is_undetermined_not_zero` |
| TRAP-31 | 上级标准器多级重复累加 | 按每份证书独立累加，u_c虚高，合格件大范围退回 | 溯源路径去重，同一证书只计一次后RSS合成 | `app/domain.py::combine_uncertainty` | `tests/test_m8.py::test_shared_reference_counted_once` |
| TRAP-32 | 共享系统偏差被当随机抵消 | 把共享上级当互不相关量平均，掩盖共同系统偏差 | 共享证书标注共同系统分量并保留在每条声明内，不跨测量抵消 | `app/modules/m8_declaration/rules.py` | `tests/test_m8.py::test_sources_and_common_components_shown` |
| TRAP-33 | 失效/超量程仍出声明 | 只读数落偏差内就出符合声明 | 失效、超量程、断链一律停止出具且无声明编号 | `app/modules/m8_declaration/rules.py` | `tests/test_m8.py::test_blocked_measurements_get_no_declaration` |
| TRAP-34 | 边界读数被误判 | 点估计压线即判符合，忽略不确定度 | 护基判定：区间整体落入偏差才符合，压线跨区间无法判定 | `app/domain.py::guard_band_verdict` | `tests/test_m8.py::test_guard_band_verdicts` |
| TRAP-35 | 重跑产生重复声明/上游变更不重算 | 每次运行新建声明，历史结论无法追溯 | 确定性声明ID幂等登记；上游变更后旧声明置“已重算”指向新编号 | `app/store.py::register_declarations` | `tests/test_m8.py::test_rerun_same_batch_creates_no_second_declaration` |

## 对账规则

输入记录 = 采信记录 + 隔离记录 + 相同行重复。重复表头与空行单独记数。业务合计按阶段中的守恒或差值列复核。运行清单有原文SHA256、规则版本与耗时；相同规则版本下同文重复提交复用批次。

M8对账：出具声明数 + 停止出具数 = 测量裁决采信记录数；登记表中“有效+已重算”声明数等于各批次出具声明累计，同批重跑不新增行。每条符合/不符合/无法判定均可回溯到测量值、允许偏差与整链依据（溯源路径、逐证书u_i、u_c、U、k、规则版本、输入SHA256）。

## 已知不覆盖

部署为本地单用户工具，不连接外部上游系统。CSV单文件5MB及一万条业务记录上限；不推断未提供的未知数据。
