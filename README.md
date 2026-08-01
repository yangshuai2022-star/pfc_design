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
| 寻优+精修 | `optimize --refine` | 网格后再用 scipy 对 Top5 种子做 (fsw×ripple) 局部精修 |
| 寻优+全局搜索 | `optimize --heuristic` | 网格后再跑差分进化,联合搜索 连续(fsw,ripple)×离散(core,MOSFET) |
| 效率地图 | `map` | 固定硬件在 电压×负载 矩阵下的效率(10-100% 负载 × 176/220/264V) |
| 拓扑对比 | `totem` | 桥式 boost vs totem-pole 无桥,同磁件对比损耗分解图 |
| 热环路 | `run --thermal` | 损耗↔温度闭环自洽,Tj/T_winding 输出 |
| 二极管数据库 | `diodes` | SiC / Si 快恢复二极管,datasheet Vf(T) 模型 |
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
--refine          网格后对 Top5 可行解做局部精修（Nelder-Mead，变量 fsw×ripple）
--heuristic       网格后跑差分进化全局搜索（fsw×ripple×core×MOSFET 联合）
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
--diode C4D10120H     指定二极管（DiodeDatabase，否则用 spec 的 Vf/Rd）
--thermal         损耗↔温度闭环（Tj_mos/Tj_dio/T_winding 自洽迭代）
--no-plot         不生成图表
```

### 效率地图选项

```
map --vin-list 176,220,264   地图电压点
map --load-list 10,25,50,75,100  负载点（% Pout）
map --core 0077004A7 --mosfet IPW65R032M8  固定硬件（额定点设计一次，全矩阵复用）
map --thermal                 含热环路
map --csv out.csv             导出 CSV
```

### 拓扑对比选项

```
totem --diode C4D10120H      桥式 boost 基线（SiC 二极管）
totem --hf-mosfet GS66516T    totem HF 桥臂器件（默认 GaN）
totem --slow-mosfet IPW65R032M8  工频桥臂器件（默认 Si SJ）
totem --deadtime 100          死区 (ns)
totem --vfb 2.0               体二极管压降 (V)
totem --plot                  损耗分解对比柱状图
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
│   ├── diodes.json                      8 款二极管 (SiC Schottky + Si 快恢复, Vf(T))
│   └── steinmetz_coefficients.json      18 种材料 Steinmetz 系数
└── tests/             verify_mathcad (8 tests)
```

## 损耗模型

### 拓扑对比 (totem-pole 无桥, `totem` 命令)

- 与桥式 boost **同磁件**对比:电感设计与 line-cycle trace 完全复用(`compute_inductor_metrics` 共享)
- HF 桥臂(默认 GS66516T GaN):主开关导通/开关损耗 + SR 通道导通损耗(1-D 时段) +
  SR 谷值关断损耗 + 死区体二极管导通(Vf_bd × t_dead × (I_valley+I_peak))
- 工频桥臂(默认 IPW65R032M8):两个器件各导通半个工频周期,总损耗 = I_rms² × Rds
- 整流桥与升压二极管完全消除;7.1kW / 65kHz 基准:
  桥式 boost 236.6W (96.77%) → totem-pole 156.9W (97.84%),省 79.7W

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
- 正向损耗: Vf(Tj) × I_avg + Rd(Tj) × I_rms²,温度插值 (25°C↔150°C datasheet 值)
- 反向恢复: Qrr(Tj) × Vout × fsw(Si 快恢复),SiC 肖特基忽略
- 器件库 `diodes.json`:C4D10120H / C6D10065A / IDH10G65C6 / STPSC10H065 / STTH12R06 等

### 热模型(可选, --thermal)
- 固定点迭代: Tj_mos = Ta + (Rth_jc+Rth_cs+Rth_sa) × P_mos,10 次内收敛到 0.1°C
- Rds(Tj)、Vf(Tj)、铜阻(T_winding) 全部参与闭环;不开启时保持 80°C 固定结温(与 Mathcad 口径一致)

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

### 2026-08-01
- 寻优算法升级：网格搜索之外新增两阶段启发式搜索
  - 共享可行性检查器 `optimization/feasibility.py`：Bmax/window/saturation/ripple 四类约束
    单一定义，sweep / refine / global search 三处共用，消除口径漂移
  - `optimize --refine`：scipy Nelder-Mead 对 Top5 可行网格种子做 (fsw×ripple) 局部精修，
    罚函数保证不可行解永远排在可行解之后；替代旧版对整数匝数的 L-BFGS-B 误用
  - `optimize --heuristic`：scipy differential_evolution 联合搜索
    连续 (fsw, ripple) × 离散 (core, MOSFET) 索引（integrality 声明），
    单次评估 ~0.3ms，全局搜索 2500 次评估约 0.6s
  - 验证：65kHz 固定网格 780 组合 0 可行解，DE 全局搜索找到
    74.8kHz/0.34 可行点 245.8W（96.65%）；60-100kHz 网格精修从 249.7W 降至 245.8W（省 3.9W）
  - 回归测试新增 `tests/test_heuristic_search.py` 6 项，全量 66 passed

### 2026-08-01 (续)
- 电感设计环修正（T1）：匝数迭代目标从"空载电感"改为"峰值电流处的有效电感
  L_eff(I_peak) ≥ 98%×L_target"，受 B_max<0.7Bsat 和窗口利用率<60% 约束；
  无法达标的磁芯如实上报 `L_eff_target_met=False` + 限制因素（droop_peak/window）。
  效果：65kHz 固定网格从 0 可行 → 221 可行（此前 ripple 规格形同虚设）
- 二极管数据库 + Vf(T) 模型（T2）：`data/diodes.json` 8 款（SiC 肖特基 + Si 快恢复），
  DiodeSpec/DiodeDatabase、Vf(25°C↔150°C) 线性插值、Qrr(Tj) 温度修正；
  `run/optimize --diode <part>`，`diodes` 命令列出器件
- 自洽热环路（T4）：`--thermal` 开启损耗↔温度固定点迭代（Tj_mos/Tj_dio/T_winding，
  10 次收敛 0.1°C），Rds(Tj)/Vf(Tj)/铜阻(T) 参与闭环；默认关闭保持 Mathcad 口径。
  演示（C4D10120H）：Tj_mos=105°C / Tj_dio=100°C / T_wind=180°C，总损耗 249.0W（96.61%）
- 效率地图（T5）：`map` 命令，额定点设计一次硬件，在 电压×负载 矩阵复用
  （analyze() 新增 design 复用参数）。176V 满载 96.6% / 264V 满载 97.8%，峰值在 ~75% 负载；
  支持 --csv 导出和效率曲线 PNG
- 回归测试：新增 `tests/test_inductor_design_loop.py`（4 项）+
  `tests/test_thermal_diode_map.py`（9 项），全量 80 passed

### 2026-08-01 (终)
- totem-pole 无桥拓扑对比（T6）：`models/totem_pole.py` + `totem` CLI 命令
  - CCM 同步整流模型：主开关（D 时段）+ SR（1-D 时段，通道导通）、SR 谷值硬关断、
    死区体二极管导通、工频桥臂 I_rms²×Rds；整流桥和升压二极管完全消除
  - 与桥式 boost 同磁件、同 fsw/ripple 对比；`compute_inductor_metrics` 提取为共享函数
  - 7.1kW/65kHz 基准：boost 236.6W（96.77%）→ totem 156.9W（97.84%），省 79.7W
    （二极管 43.5W + 整流桥 75.7W 消除，GaN 功率级净增 43.5W）
  - `--plot` 输出损耗分解对比柱状图；支持 --thermal 热环路
  - 回归测试 `tests/test_totem_pole.py`（7 项，含代数恒等校验），全量 87 passed


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
