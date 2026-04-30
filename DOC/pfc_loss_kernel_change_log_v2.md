# PFC 双时间尺度损耗内核：公式审查后的变更清单 v2

> 目标：把当前 `pfc_design` 从“单点/峰值近似损耗计算器”，升级为“工频周期积分 + 高频开关周期局部平均”的 PFC 可信损耗内核。
>
> 适用对象：单相两相交错 Boost PFC，CCM/近似 CCM，低线满载为主要热与损耗校核工况。

---

## 1. 这次审查后的核心改变

原方案里虽然已经有 `OperatingPoint` 半个工频周期数组，但多个损耗模型仍然混合了：

- 单点峰值计算；
- 简化 RMS 估算；
- 每相功率与整机功率口径混用；
- 用 DC/DC 思维估算 PFC 损耗。

新的原则改为：

```text
PFC 每一个损耗项 = 工频半周积分 [ 高频开关周期局部平均损耗 ]
```

即：

```text
θ ∈ [0, π]
Vin(θ) = Vm · sin(θ)
Iavg(θ) = Ipk · sin(θ)
D(θ) = 1 - Vin(θ) / Vout
ΔIL(θ) = Vin(θ) · D(θ) / (L · fsw)

P_loss_avg = (1/π) · ∫_0^π P_local(θ) dθ
```

这不是优化项，而是 P0 级公式架构变更。

---

## 2. 当前代码状态判断

### 2.1 已有基础

当前 `OperatingPoint` 已经生成：

- 半个工频周期时间数组；
- `vac_t`；
- `duty_t`；
- `iin_t`；
- `rms()` / `avg()` 积分函数。

这说明项目已经具备做双时间尺度损耗计算的基础，不需要从零重写。

### 2.2 需要立即改的地方

| 模块 | 当前问题 | 必须改成 |
|---|---|---|
| `inductor._calculate_L()` | `L = Vm/(r·fsw·Iin_rms)`，缺少 Boost duty，纹波定义不清 | `L = Vin_pk_min·D_pk/(fsw·ΔIL_pp_ref)` |
| `inductor._core_loss()` | 只在低线峰值点算 `Bac`，再用 OSE | 对 `ΔB(θ)` 做工频积分；第一版可 OSE-by-point，第二版 iGSE |
| `inductor._copper_loss()` | 把总 RMS 电流乘高频 AC 系数 | 低频主电流用 `Rdc`；高频纹波 RMS 用 `Rac(fsw)` |
| `mosfet._switching_loss()` | 用 `2/π·Ipk` 一个平均电流点 | 对 `Eon/Eoff(V,I,T)` 或 `0.5·V·I·t` 做工频积分 |
| `mosfet._conduction_loss()` | 有 duty 积分基础，但未显式加入三角纹波 RMS | `D(θ)·[Iavg(θ)^2 + ΔI(θ)^2/12]` 积分 |
| `diode._forward_loss()` | 有 off-duty 积分基础，但未加入三角纹波 RMS | `(1-D(θ))·[Iavg(θ)^2 + ΔI(θ)^2/12]` 积分 |
| `bridge_rectifier.py` | 使用 `op.iin_rms`，但桥堆是共享整机部件 | 用整机输入总电流口径 |
| `capacitor.py` | 低频纹波使用 `pout_per_phase` | 用整机 `pout_total`；高频纹波要考虑两相交错抵消 |
| `system.py` | 结果聚合区分了 per-phase 与 shared，但 shared 模型输入口径不统一 | 建立明确的 `per_phase` 与 `total` 变量命名规范 |

---

## 3. 新增核心对象：LineCycleTrace

建议新增文件：

```text
core/line_cycle.py
```

建议数据结构：

```python
@dataclass
class LineCycleTrace:
    theta: np.ndarray
    sin_theta: np.ndarray
    vin_abs: np.ndarray
    duty: np.ndarray
    i_avg_phase: np.ndarray
    delta_i_pp: np.ndarray
    i_peak: np.ndarray
    i_valley: np.ndarray
    i_rms_switch_period_sq: np.ndarray
    dtheta: float
```

核心公式：

```python
sin_theta = np.maximum(np.sin(theta), sin_min)
vin_abs = vm * sin_theta

duty = 1.0 - vin_abs / vout
duty = np.clip(duty, duty_min, duty_max)

i_avg_phase = sqrt(2) * iin_rms_phase * sin_theta

delta_i_pp = vin_abs * duty / (L_eff_or_target * fsw)

i_peak = i_avg_phase + 0.5 * delta_i_pp
i_valley = i_avg_phase - 0.5 * delta_i_pp

i_rms_sw_sq = i_avg_phase**2 + delta_i_pp**2 / 12.0
```

注意：

1. `sin_min` 只用于数值保护，不应改变物理积分太多。
2. 过零附近如果进入 DCM，应输出风险标记：`near_zero_or_dcm_region`。
3. 第一版可以仍按 CCM 处理，但必须把 CCM/DCM 边界标出来。

---

## 4. Boost 电感设计公式修正

### 4.1 当前公式问题

当前：

```text
L = Vm / (ripple_ratio × fsw × Iin_rms)
```

问题：

- 缺少 Boost 占空比 `D`；
- `ripple_ratio` 参考对象不清；
- 不能正确反映 `Vout` 对电感值的影响；
- 后续 Bmax、ΔB、铜损、开关电流都会被带偏。

### 4.2 新公式

建议定义：

```text
ripple_ratio = ΔIL_pp_at_line_peak / Iin_peak_phase
```

则：

```text
Vin_pk_min = sqrt(2) · Vin_rms_min
D_pk = 1 - Vin_pk_min / Vout
Iin_rms_phase = Pout_total / n_phases / eta / Vin_rms_min
Iin_pk_phase = sqrt(2) · Iin_rms_phase
ΔIL_pp_ref = ripple_ratio · Iin_pk_phase
L_target = Vin_pk_min · D_pk / (fsw · ΔIL_pp_ref)
```

这比原公式更符合 Boost PFC 的物理过程。

---

## 5. MOSFET 损耗改法

### 5.1 导通损耗

改成对工频半周积分：

```text
P_cond = Rds_on(Tj) · meanθ{ D(θ) · [Iavg(θ)^2 + ΔI(θ)^2/12] }
```

注意：

- 这是每相每个 Boost MOSFET 的损耗；
- 若一相有并联 MOSFET，需要加入电流分配系数；
- 后续加入热迭代：`Tj -> Rds_on(Tj) -> Pcond -> Tj`。

### 5.2 开关损耗

第一版：

```text
Eon(θ)  = 0.5 · Vout · Ion(θ) · tr
Eoff(θ) = 0.5 · Vout · Ioff(θ) · tf
Psw = fsw · meanθ{ Eon(θ) + Eoff(θ) }
```

建议：

```text
Ion/Ioff 可先使用 i_peak(θ) 或 i_avg(θ)，但必须在 metadata 中说明。
```

第二版：

```text
Eon/Eoff = lookup_table(Vds, Id, Rg, Tj)
Psw = fsw · meanθ{ Eon(Vout, I_on(θ), Tj) + Eoff(Vout, I_off(θ), Tj) }
```

### 5.3 Coss/Eoss

第一版：

```text
P_eoss = Eoss(Vout) · fsw
```

但要注意：

- 如果 datasheet 的 `Eoff` 已包含 Coss 相关能量，不能再重复加完整 Eoss；
- 数据库必须增加 `loss_accounting_note` 字段。

---

## 6. Boost 二极管损耗改法

### 6.1 正向损耗

```text
P_diode_fwd = meanθ{ Vf · (1-D(θ)) · Iavg(θ) }
             + Rd · meanθ{ (1-D(θ)) · [Iavg(θ)^2 + ΔI(θ)^2/12] }
```

### 6.2 反向恢复 / 结电容损耗

Si 快恢复：

```text
P_rr = fsw · meanθ{ Qrr(I,T,di/dt) · Vout }
```

SiC：

```text
传统 Qrr 可近似为 0，但仍应考虑 Cj/Qc/Ec 相关损耗。
```

因此不能简单写成“SiC = 0 动态损耗”，只能写成“忽略传统反向恢复损耗”。

---

## 7. 电感磁芯损耗改法

### 7.1 第一版：line-cycle OSE

每个工频角度点：

```text
ΔB_pp(θ) = L_eff · ΔI_pp(θ) / (N · Ae)
B_ac_peak(θ) = ΔB_pp(θ) / 2
Pcore_density(θ) = k · fsw^α · B_ac_peak(θ)^β
Pcore_avg = Ve · meanθ{ Pcore_density(θ) }
```

这比只取低线峰值点更合理。

### 7.2 第二版：line-cycle iGSE

每个角度点使用该开关周期内的三角磁通波形，按 iGSE 计算局部损耗，然后再对工频半周积分。

### 7.3 必须输出模型风险

```text
core_loss_model = line_cycle_ose / line_cycle_igse / vendor_curve
confidence = low / medium / high
risk_flags:
- Steinmetz coefficients source unknown
- DC bias not included in core loss coefficient
- non-sinusoidal excitation
- temperature not iterated
```

---

## 8. 绕组损耗改法

不能把总 RMS 电流全部乘高频 AC 系数。

建议：

```text
Pcu_line = Irms_line_phase^2 · Rdc(T)

Irms_ripple_hf_sq = meanθ{ ΔI_pp(θ)^2 / 12 }
Pcu_hf = Irms_ripple_hf_sq · Rac(fsw, geometry, T)

Pcu_total = Pcu_line + Pcu_hf
```

其中：

```text
Rac = Rdc · F_skin · F_prox
```

第一版可以仍然使用现有 `skin_effect_factor()` 和 `proximity_factor()`，但报告必须说明这是简化估算模型。

---

## 9. 输出电容改法

PFC 输出电容不能只算一个简单电容纹波。

必须拆成：

```text
1. 二倍工频功率脉动电流；
2. 高频 Boost 开关纹波；
3. 两相交错后的高频纹波抵消；
4. ESR 损耗；
5. 热与寿命估算。
```

低频电压纹波使用整机功率：

```text
ΔV_lf_pp ≈ Pout_total / (2π · f_line · C · Vout)
```

注意：这里是整机 `Pout_total`，不是 `pout_per_phase`。

---

## 10. 新增输出：loss_trace.csv

每次 `run` 或 `optimize --trace` 应输出：

```text
theta_deg
vin_abs
phase_i_avg
duty
delta_i_pp
i_peak
i_valley
mosfet_cond_density
mosfet_sw_density
diode_cond_density
core_loss_density
winding_line_density
winding_hf_density
```

目的：

- 审查公式；
- 发现异常角度；
- 画损耗分布图；
- 方便跟 Mathcad/PLECS/实测波形对比。

---

## 11. 新增测试任务

建议新增：

```text
tests/test_line_cycle_trace.py
tests/test_boost_inductor_formula.py
tests/test_mosfet_two_timescale_loss.py
tests/test_diode_two_timescale_loss.py
tests/test_inductor_line_cycle_core_loss.py
tests/test_winding_loss_split.py
tests/test_shared_component_power_basis.py
```

必须测试：

1. `L_target` 与手算公式一致；
2. `ΔI_pp(θ)` 在低线峰值处等于目标纹波；
3. `i_peak = i_avg + ΔI/2`；
4. MOSFET 导通损耗在 `ΔI=0` 时退化为 `Rds·mean(D·I²)`；
5. 绕组损耗在 `ΔI=0` 时没有高频铜损；
6. 输出电容低频纹波使用整机功率；
7. 桥堆损耗使用整机输入电流。

---

## 12. 给 Codex 的第一批开发任务

### Task 1：新增 `core/line_cycle.py`

实现 `LineCycleTrace` 和 `build_line_cycle_trace()`。

### Task 2：修正电感设计公式

改 `InductorDesigner._calculate_L()`，并在 metadata 里输出：

```text
Vin_pk_min
D_at_line_peak
Iin_rms_phase
Iin_pk_phase
DeltaI_pp_ref
ripple_definition
```

### Task 3：改造电感损耗

新增：

```text
_core_loss_line_cycle_ose()
_copper_loss_split()
```

保留旧模型作为 `legacy`，用于对比。

### Task 4：改造 MOSFET 损耗

新增：

```text
_conduction_loss_line_cycle()
_switching_loss_line_cycle_trtf()
```

### Task 5：改造二极管损耗

新增：

```text
_forward_loss_line_cycle()
_reverse_recovery_line_cycle()
```

### Task 6：修正 shared component 口径

桥堆与输出电容统一使用整机总功率/总电流。

### Task 7：输出 trace

CLI 增加：

```bash
python -m pfc_design run --trace
```

输出：

```text
output/loss_trace.csv
```

---

## 13. 不建议立刻做的事

暂时不要先做：

- GUI；
- 通用 Agent；
- 多拓扑扩展；
- 自动抓 datasheet；
- PLECS 自动生成；
- 过度复杂的机器学习模型。

现在最优先的是把 PFC 损耗内核做准。

---

## 14. 当前阶段的准确产品定位

更准确的说法是：

```text
本项目当前目标不是“一键设计电源”，而是建立一个可信的 PFC 设计空间探索内核。

它通过双时间尺度损耗积分、器件数据库、工程约束和自动寻优，
把传统依赖 Excel/Mathcad/经验试算的流程，升级为模型驱动、数据驱动、可验证的工程设计流程。
```

