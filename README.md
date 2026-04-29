# PFC Design Calculator

两相交错式 PFC（功率因数校正）设计计算器，用于 6.6kW OBC 的工程设计、损耗分析和参数寻优。

控制方式：UCC28070A 平均电流模式

## 快速开始

```powershell
cd C:\Users\yangs\py
pip install numpy scipy matplotlib pandas click rich
python -m pfc_design run          # 单点设计分析
python -m pfc_design optimize     # 参数寻优
python -m pfc_design mosfets      # 查看 MOSFET 数据库
python -m pfc_design cores        # 查看磁芯数据库
```

## 功能清单

| 功能 | 命令 | 说明 |
|------|------|------|
| 单点设计 | `run` | 完整损耗分析 + 饼图 + LvsI 饱和曲线 |
| 参数寻优 | `optimize` | 四维网格搜索 (fsw × ripple × core × MOSFET) |
| 固定频率寻优 | `optimize --fsw 65` | fsw 固定 65kHz，扫其他维度 |
| 默认寻优 | `optimize` | 默认只搜 Si MOSFET（Si CoolMOS + Si SuperJunction） |
| 筛选技术 | `optimize --tech SiC` | 只搜 SiC MOSFET |
| 全技术搜索 | `optimize --tech all` | SiC + Si CoolMOS + SJ + GaN |
| 磁芯列表 | `cores` | 按材料筛选磁环 |
| MOSFET 列表 | `mosfets` | 按技术筛选 MOSFET |

### 寻优选项

```
--fsw 65          固定开关频率(kHz)，不扫描
--tech Si         仅搜索 Si MOSFET（默认，Si CoolMOS + Si SuperJunction）
--tech all        搜索所有 MOSFET 技术
--tech SiC        仅 SiC MOSFET
--top 10          显示前 10 最优结果
--n-cores 2       堆叠磁芯数量
```

### 单点设计选项

```
--vin 220         输入电压 (Vrms)
--vout 410        输出电压 (Vdc)
--pout 6600       输出功率 (W)
--fsw 100000      开关频率 (Hz)
--ripple 0.3      纹波比
--core 0077083A7  指定磁芯
--mosfet IMW65R048M1H  指定 MOSFET
--no-plot         不生成图表
```

## 架构

```
pfc_design/
├── core/              spec (DesignSpec+MosfetSpec), operating_point, constants
├── magnetics/         core_database, steinmetz (OSE/MSE/iGSE), saturation, winding
├── models/            inductor, mosfet, diode, bridge_rectifier, capacitor, system
├── optimization/      design_space, sweep (grid search), pareto, scipy_opt
├── plotting/          losses (pie), inductor (LvsI), efficiency, sweep_viz
├── report/            console (Rich tables), pdf_report
├── data/
│   ├── cores.json                       33 种磁环 (Kool Mu, MPP, HighFlux, Ferrite...)
│   ├── mosfets.json                     21 款 MOSFET (SiC + Si CoolMOS + SJ + GaN)
│   └── steinmetz_coefficients.json      18 种材料 Steinmetz 系数
└── tests/             verify_mathcad (8 tests)
```

## 损耗模型

### 电感
- **磁芯损耗**: Steinmetz OSE — P_fe = k × f^α × B_ac^β × Ve
- **铜损**: Rdc × Irms² × F_skin × F_prox（集肤 + Dowell 邻近效应，磁环分布式绕组）
- **饱和模型**: DC bias 多项式 — %μi = f(H_dc)，L_eff = L₀ × %μi
- **匝数迭代**: B_max < 0.7×B_sat 约束下自动调整匝数

### MOSFET
- 导通损耗: I_ds_rms² × Rds_on(Tj)（含温度修正）
- 开关损耗: fsw × (Eon + Eoff)，半周期积分
- Coss 损耗: ½ × Coss_er × Vout² × fsw
- 栅极驱动: Qg × Vgs × fsw

### 二极管
- 正向损耗: Vf × I_avg + Rd × I_rms²
- 反向恢复: Qrr × Vout × fsw（SiC 忽略）

### 电容
- 低频纹波: ΔVpp = Iout / (2π × f_line × C)
- ESR 损耗: Ic_rms² × ESR_parallel
- 寿命: Arrhenius — L = L_rated × 2^((T_rated-T_core)/10) × (I_rated/I)^n

## 寻优策略

1. 笛卡尔积: fsw × ripple_ratio × core × mosfet
2. 每个组合计算完整损耗
3. 约束检查:
   - B_max < 0.7×B_sat（磁饱和）
   - 窗口利用率 < 60%（绕线可行性）
   - L_eff > 20%×L₀（不严重饱和）
4. 按总损耗排序 → Top N 对比表 + 效率 Plateau 散点图

## 开发日志

### 2026-04-30
- 将优化目标明确为“工程约束下的系统总损耗最小”，默认按 `P_total_W` 对可行解排序
- `optimize` 默认只搜索 Si MOSFET（`Si CoolMOS` + `Si SuperJunction`），需要全技术比较时显式使用 `--tech all`
- 增加 `--core-material`、`--core-limit`、`--csv` 寻优选项，支持控制磁芯候选范围并导出完整 sweep 结果
- 修复 `--tech` 参数只影响显示、不影响实际 sweep 的问题；CLI 选出的 MOSFET 候选现在会传入 `ParamSweep`
- 扫描结果新增细分损耗字段：电感铁损/铜损、MOSFET 导通/开关/Coss/驱动、二极管正向/反恢复、整流桥、电容 ESR
- 修正电感设计中 `L_eff_at_ipeak_uh` 使用 RMS 偏置值的问题，现在按峰值电流下的有效电感计算 Bmax 和饱和比例
- 修复项目 `pyproject.toml` 打包配置，支持 `py -3 -m pip install -e .` 安装运行
- 新增公众号发布说明文档 `DOC/pfc_design_calculator_article.md`，说明软件目的、实现细节、寻优思路和 CLI 使用方式
- 验证默认 Si MOSFET 固定 65kHz 寻优：1040 个组合、52 个可行点，当前最优点约 213.0W 系统损耗、97.09% 效率
- 回归测试 `tests/verify_mathcad.py` 通过：8 passed

### 2026-05-04
- 磁芯损耗从 iGSE 切换为 OSE（iGSE 的 ki 归一化系数有误）
- 寻优窗口利用率约束从 40% 放宽到 60%（磁环绕线实际可行）
- 修复 B_max 约束检查（之前错误乘以匝数）
- 增加固定 fsw 寻优选项 `--fsw 65`
- 增加 8 款 SJ MOSFET（32-68mΩ：Infineon IPW65RxxxM8, ST STWxxx, ON Semi FCHxxx）
- MOSFET 数据库共 21 款（5 SiC + 3 Si CoolMOS + 10 SJ + 2 GaN + 1 参考模型）

### 2026-05-03
- 初始版本：Mathcad PFC 计算书 → Python
- 磁芯数据库 33 款、Steinmetz 18 种材料
- 四维寻优引擎、Pareto 前沿提取
- Rich 控制台表格、损耗饼图、LvsI 饱和曲线

## 验证

对照 Mathcad PDF 原值回归测试（8 项）：

| 测试项 | Mathcad | 本工具 | 偏差 |
|--------|---------|--------|------|
| Iin_rms | 21.011A | 21.011A | 0% |
| Dmin | 0.393 | 0.393 | 0% |
| P_bridge | 37.83W | 37.83W | 0% |
| Efficiency | 96.7% | 96.6% | -0.1% |

```bash
python -m pytest pfc_design/tests/verify_mathcad.py -v
# 8 passed
```
