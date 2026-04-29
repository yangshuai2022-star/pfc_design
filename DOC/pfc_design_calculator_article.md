# 两相交错 PFC 自动计算与系统损耗寻优工具：从实现细节到使用方法

## 0. 这篇文章说明什么

这篇说明面向两个读者：

第一类是想直接使用工具的人。你需要知道命令怎么敲、输入参数是什么意思、输出结果怎么看。

第二类是想判断工具是否可信的人。你需要知道程序内部到底怎么算，电感、MOSFET、二极管、整流桥、电容分别用了什么模型，寻优为什么能找到“系统总损耗最小”的方案，而不是只找到了某个局部漂亮的单点。

本文对应的软件工程是 `pfc_design`，它是一个两相交错式 Boost PFC 设计计算与寻优工具。当前主要服务于 OBC 前级 PFC 的设计早期选型，默认设计点接近：

```text
输入电压：176-264 Vac
输出电压：410 Vdc
输出功率：7100 W
相数：2
工频：50 Hz
默认开关频率：65 kHz
默认 MOSFET 搜索范围：Si MOSFET
```

这里说的 Si MOSFET，包含数据库中的 `Si CoolMOS` 和 `Si SuperJunction`。软件默认不把 SiC 和 GaN 放入寻优，是有意为之：先给出一个更贴近成本和量产现实的硅器件基准方案，再由工程师决定是否用 `--tech all` 做宽禁带器件横向比较。

## 1. 这个工具要解决的核心问题

传统的 PFC 设计计算，通常是工程师在 Mathcad、Excel 或本地计算表格里做参数迭代。这个方式并不是不好，相反，它凝结了很多工程经验：工程师知道先调什么、哪些参数敏感、哪些组合大概率不靠谱，也知道什么时候应该保守一点。

但这种方法有一个天然限制：寻优路径很依赖个人经验。

一个工程师可能先固定频率，再调电感；另一个工程师可能先选磁芯，再换 MOSFET；有人习惯围绕历史方案微调，有人会更激进地换材料、换纹波比。最终设计结果往往是“经验驱动下的有限次数迭代”，而不是对完整设计空间的系统搜索。

这个软件想传递的核心价值观是：不要让工程师的大量精力消耗在重复试算上，而应该把工程经验固化成边界条件、器件数据库、约束规则和评价指标，让程序自动完成多维度扫描和系统损耗排序。工程师仍然做最终判断，但判断建立在更完整、更可复盘的数据空间上。

也就是说，它不是把 Mathcad 或 Excel 简单搬到 Python，而是把传统“人脑引导的手动迭代”升级为：

```text
工程经验定义边界
程序枚举设计空间
模型计算每个组合
约束筛掉不可行方案
系统总损耗排序
工程师复核最佳实践点
```

PFC 设计里，单点计算不难，困难的是系统取舍。

比如开关频率提高：

```text
电感目标值下降
匝数可能减少
电感体积可能下降
MOSFET 开关损耗增加
磁芯损耗增加
Coss 损耗增加
EMI 压力可能增加
```

纹波比增大：

```text
目标电感下降
绕线窗口压力下降
峰值电流上升
Bmax 变化
电流 RMS 与铜损变化
控制裕量和纹波电流应力变化
```

换 MOSFET：

```text
Rds_on 影响导通损耗
Qg 影响驱动损耗
Coss_er 影响输出电容损耗
tr/tf 影响开关损耗
技术路线影响成本、驱动和供应链
```

换磁芯：

```text
AL 影响匝数
Ae 影响 Bmax
Ve 影响磁芯损耗
le 影响 Hdc 和 DC bias 后的 L_eff
窗口面积影响绕线可制造性
材料影响 Steinmetz 损耗
```

所以这个工具的目标不是只回答“这个设计点能不能算”，而是回答：

```text
在给定输入输出规格、频率范围、纹波范围、磁芯数据库、MOSFET 数据库和工程约束下，
哪些组合可行？
其中哪个组合系统总损耗最小？
损耗主要来自哪里？
下一步应该优化哪个器件或哪条设计边界？
```

这就是它的核心价值：从依赖个人路径的单点迭代，推进到可解释、可重复、可扩展的系统级寻优。

## 2. 软件的价值取向

这个软件的取向比较明确：

1. 把传统经验从“个人试算路径”转化为“可执行的扫描边界和约束规则”。
2. 以系统总损耗为最终排序目标，而不是只看 MOSFET 或电感。
3. 先筛工程约束，再比较效率。
4. 默认只搜索 Si MOSFET，先建立传统硅方案基准。
5. 每个候选点保留完整细分损耗，而不是只输出一个效率数字。
6. 搜索过程采用离散网格扫描，让每个结果都可以复盘。
7. 计算模型保持透明，公式、字段和代码结构尽量一一对应。

这类工具不应该变成一个黑箱。功率硬件设计最终还要经过磁件样品、热测试、EMI 测试、环路调试和安规验证。软件的价值在于缩小前期搜索范围，减少重复计算，把明显不合适的组合提前排除。

这也是它和传统 Mathcad/Excel 表格的主要区别。表格更适合做单个设计点的推导和检查；这个工具更适合做多维组合的自动比较。两者并不冲突：Mathcad 可以作为模型来源和校验基准，Python 程序负责把模型批量化、数据库化和寻优化。

## 3. 工程目录和模块分工

工程结构如下：

```text
pfc_design/
├── __main__.py                    CLI 入口，run/optimize/mosfets/cores 命令
├── core/
│   ├── spec.py                    DesignSpec、MosfetSpec、MosfetDatabase
│   ├── operating_point.py         半工频周期工作点计算
│   └── constants.py               单位和物理常量
├── magnetics/
│   ├── core_database.py           磁芯数据库加载、筛选、Steinmetz 系数加载
│   ├── core_entry.py              CoreSpec 磁芯字段与派生几何量
│   ├── saturation.py              DC bias、L_eff、Bmax、Bac
│   ├── steinmetz.py               OSE/MSE/iGSE 磁芯损耗公式
│   └── winding.py                 集肤、邻近效应、线阻
├── models/
│   ├── inductor.py                电感设计、电感损耗
│   ├── mosfet.py                  MOSFET 损耗
│   ├── diode.py                   Boost 二极管损耗
│   ├── bridge_rectifier.py        输入整流桥损耗
│   ├── capacitor.py               输出电容 ESR、纹波和寿命估算
│   └── system.py                  系统级损耗聚合
├── optimization/
│   ├── sweep.py                   fsw/ripple/core/mosfet 四维扫描
│   ├── pareto.py                  Pareto 辅助函数
│   └── design_space.py            默认扫描空间定义
├── data/
│   ├── cores.json                 磁芯数据库
│   ├── mosfets.json               MOSFET 数据库
│   └── steinmetz_coefficients.json Steinmetz 系数
└── tests/
    └── verify_mathcad.py          Mathcad 对照回归测试
```

真正的计算主链路只有三段：

```text
CLI 参数
  -> DesignSpec + 候选 core/mosfet
  -> ParamSweep.sweep()
  -> SystemAnalyzer.analyze()
  -> 各器件 LossModel
  -> DataFrame 排序输出
```

也就是说，`optimize` 不是另外写了一套估算逻辑，而是对每一个候选组合都调用同一个系统分析器。单点计算和寻优计算使用的是同一套损耗模型。

## 4. CLI 到内部对象的执行路径

以这条命令为例：

```powershell
py -3 -m pfc_design optimize --fsw 65 --ripple-start 0.3 --ripple-stop 1.0 --ripple-n 8 --core-limit 10 --top 10
```

程序首先进入 `__main__.py` 中的 `optimize()` 函数。

这个函数做几件事：

```python
spec = DesignSpec(vin_min=vin, vout=vout, pout_total=pout)
db = CoreDatabase()
mdb = MosfetDatabase()
cores = db.top_for_pfc(ae_min_cm2=0.5, material_class=core_material, n=core_limit)
mosfets = mdb.query(vds_min=spec.vout * 1.25, technology=tech)
```

这里有几个实现细节很重要。

第一，`DesignSpec` 只保存规格，不保存计算结果。它是后续所有模型的统一输入。

第二，磁芯候选来自：

```python
CoreDatabase.top_for_pfc(ae_min_cm2=0.5, material_class="Sendust", n=10)
```

默认会取前 10 个 Sendust 磁芯候选。

第三，MOSFET 候选来自：

```python
MosfetDatabase.query(vds_min=spec.vout * 1.25, technology="Si")
```

默认技术筛选是 `Si`。在 `MosfetDatabase.query()` 里，`Si` 是一个别名，包含：

```text
Si CoolMOS
Si SuperJunction
```

但不包含：

```text
SiC
GaN
```

如果命令中写 `--tech all`，技术筛选才会关闭。

第四，`--fsw 65` 在 `optimize` 命令里单位是 kHz。代码中会转换成 Hz：

```python
fsw_arr = np.array([fsw * 1000])
```

如果不指定 `--fsw`，则使用：

```python
np.arange(fsw_start * 1000, (fsw_stop + fsw_step/2) * 1000, fsw_step * 1000)
```

也就是扫描一个开关频率数组。

第五，纹波比数组来自：

```python
np.linspace(ripple_start, ripple_stop, int(ripple_n))
```

比如：

```text
--ripple-start 0.3
--ripple-stop 1.0
--ripple-n 8
```

得到的是 8 个纹波比点。

最后，CLI 构造一个四维扫描变量：

```python
sweep_vars = {
    "fsw": fsw_arr,
    "ripple_ratio": np.linspace(ripple_start, ripple_stop, int(ripple_n)),
    "core_idx": list(range(len(cores))),
    "mosfet_idx": list(range(len(mosfets))),
}
```

如果固定 65 kHz，8 个纹波点，10 个磁芯，13 个默认 Si MOSFET，则扫描点数是：

```text
1 * 8 * 10 * 13 = 1040
```

这就是命令行里看到的：

```text
Total points: 1040
```

## 5. DesignSpec：所有设计输入的单一入口

`DesignSpec` 位于 `core/spec.py`，它是所有模型的输入根对象。主要字段如下：

```python
vin_min: float = 176.0
vin_max: float = 264.0
vin_nom: float = 220.0
vout: float = 410.0
pout_total: float = 7100.0
n_phases: int = 2
f_line: float = 50.0
fsw: float = 65_000.0
ripple_ratio: float = 1.0
eta_target: float = 0.96
```

电感约束：

```python
L_target: Optional[float] = None
B_max_target: float = 0.25
J_max: float = 6.0
core_material_pref: str = "Sendust"
```

二极管与整流桥：

```python
diode_vf: float = 1.5
diode_rd: float = 0.1
diode_type: str = "SiC"
bridge_vf: float = 1.0
```

电容：

```python
c_out_total: float = 1320e-6
cap_esr: float = 0.15
cap_n_parallel: int = 4
cap_rated_ripple: float = 3.0
cap_rated_temp: float = 105.0
cap_rated_life: float = 5000.0
cap_ambient: float = 45.0
```

相功率通过属性计算：

```python
pout_per_phase = pout_total / n_phases
```

这种设计的好处是后续所有模型都不需要重新解释输入参数。每个模型只从同一个 `DesignSpec` 读自己需要的字段。

## 6. OperatingPoint：半个工频周期的波形计算

`OperatingPoint` 位于 `core/operating_point.py`。

它的作用是根据设计规格，在低线输入下生成半个工频周期的离散波形。当前离散点数：

```python
N_PTS = 200
```

时间轴：

```python
self.t = np.linspace(0, 0.5 / spec.f_line, N_PTS)
theta = self.omega * self.t
```

输入电压：

```python
vm = sqrt(2) * vin_rms
vac_t = vm * abs(sin(theta))
```

Boost 占空比：

```python
duty_t = 1.0 - vac_t / spec.vout
duty_t = clip(duty_t, 0.02, 0.98)
```

输入电流：

```python
pin_per_phase = spec.pout_per_phase / spec.eta_target
iin_rms = pin_per_phase / vin_rms
iin_peak = sqrt(2) * iin_rms
iin_t = iin_peak * abs(sin(theta))
```

这个对象还提供两个积分函数：

```python
rms(waveform, duty_mod=None)
avg(waveform, duty_mod=None)
```

比如 MOSFET 导通电流 RMS 就通过：

```python
op.rms(op.iin_t, op.duty_t)
```

这里的 `duty_mod` 是一个很关键的实现：它让程序能在半个工频周期上计算“某个器件只在部分开关周期导通”的等效 RMS 或平均电流。

## 7. SystemAnalyzer：系统损耗的总调度器

`SystemAnalyzer` 位于 `models/system.py`。它不是具体某个器件模型，而是系统级调度器。

初始化时，它创建所有子模型：

```python
self.inductor_designer = InductorDesigner(self.db)
self.inductor_loss = InductorLoss(self.db)
self.mosfet_loss = MosfetLoss()
self.diode_loss = DiodeLoss()
self.bridge_loss = BridgeRectifierLoss()
self.capacitor = CapacitorBank()
```

单次分析路径：

```python
op = compute_mathcad_operating_point(spec)
design = self.inductor_designer.design(spec, op, preferred_core, n_cores)
ind_loss = self.inductor_loss.compute(design, spec, op)
mos_loss = self.mosfet_loss.compute(spec, op, mosfet=mosfet)
dio_loss = self.diode_loss.compute(spec, op)
br_loss = self.bridge_loss.compute(spec, op)
cap_loss = self.capacitor.compute(spec, op)
```

系统总损耗汇总：

```python
per_phase_loss = ind_loss.power_loss_W + mos_loss.power_loss_W + dio_loss.power_loss_W
total_loss = spec.n_phases * per_phase_loss + br_loss.power_loss_W + cap_loss.power_loss_W
efficiency = spec.pout_total / (spec.pout_total + total_loss)
```

这里有个设计细节：电感、MOSFET、Boost 二极管是每相都有的，所以乘以 `n_phases`；整流桥和输出电容是系统共享的，所以只加一次。

系统还会生成细分损耗表：

```python
breakdown = {
    "Inductor Core": n * ind_loss.sub_losses["core"],
    "Inductor Copper": n * ind_loss.sub_losses["copper"],
    "MOSFET Conduction": n * mos_loss.sub_losses["conduction"],
    "MOSFET Switching": n * mos_loss.sub_losses["switching"],
    "MOSFET Coss": n * mos_loss.sub_losses.get("Coss", 0),
    "MOSFET Gate Drive": n * mos_loss.sub_losses.get("gate_drive", 0),
    "Diode Forward": n * dio_loss.sub_losses["forward"],
    "Diode RR": n * dio_loss.sub_losses.get("reverse_recovery", 0),
    "Bridge Rectifier": br_loss.power_loss_W,
    "Capacitor ESR": cap_loss.power_loss_W,
}
```

这就是为什么最后输出能看到每个损耗来源，而不是只有一个效率。

## 8. 电感设计：从目标 L 到实际 L_eff

电感设计位于 `models/inductor.py`。

### 8.1 目标电感计算

如果用户没有手动指定 `L_target`，程序使用：

```python
L_target_uh = op.vm / (spec.ripple_ratio * spec.fsw * op.iin_rms) * 1e6
```

也就是：

```text
L = Vm / (ripple_ratio * fsw * Iin_rms)
```

这里用的是低线输入下的 `Iin_rms`，和当前 Mathcad 计算书保持一致。

### 8.2 磁芯选择

如果 CLI 或寻优器传入 `preferred_core`，就直接使用该磁芯。优化扫描时，每一个 `core_idx` 都会指定一个具体磁芯。

如果没有指定磁芯，程序会根据 `Ae*N` 估算值筛选：

```python
ae_n = self._required_ae_n(spec, op)
ae_min = ae_n / 60
candidates = self.db.query(
    material_class=spec.core_material_pref,
    ae_min_cm2=ae_min * 0.5,
    max_results=20
)
```

其中 `_required_ae_n()` 根据半个工频周期的电压时间积估算需要的 `Ae*N`：

```python
v_d_product = op.vac_t * op.duty_t
v_s_per_cycle = trapezoid(v_d_product, op.t) / spec.fsw
half_period = 0.5 / spec.f_line
AeN = v_s_per_cycle / (half_period * b_target)
```

### 8.3 匝数计算

磁芯数据库提供 `AL`，单位是 nH/turn^2。若有多个磁芯堆叠：

```python
al_total = core.al_nH_per_t2 * n_cores
n_turns = round(sqrt(L_target_uh * 1000 / al_total))
```

实际空载电感：

```python
L_noload_uh = al_total * n_turns**2 / 1000
```

### 8.4 DC bias 后的有效电感

DC bias 计算位于 `magnetics/saturation.py`。

磁场强度：

```python
H_oe = 0.4 * pi * N * I / le_cm
```

磁导率百分比使用数据库里的多项式：

```python
%ui = c0 + c1*H + c2*H^2 + c3*H^3 + c4*H^4
```

代码中用：

```python
pct = np.polyval(list(reversed(coeffs)), h_oe)
pct = clip(pct, 1.0, 100.0)
L_eff = L0 * pct / 100
```

当前版本的关键修正是：用于结果输出和 Bmax 检查的 `L_eff_at_ipeak_uh` 已经改成峰值电流下的有效电感：

```python
L_eff_peak = effective_inductance(L_noload_uh, n_turns, op.iin_peak, ...)
```

这比用 RMS 电流更保守，也更适合判断峰值磁通。

### 8.5 Bmax 迭代

峰值磁通密度：

```python
Bmax = L_eff_peak * Ipeak / (N * Ae_total)
```

代码对应：

```python
b_peak = calculate_b_max(L_eff_peak, op.iin_peak, n_turns, core.ae_cm2 * n_cores)
safe_b = core.bs_T * 0.7
```

如果超过安全磁通：

```python
while b_peak > safe_b and iterations < 20:
    n_turns += 1
    recalculate L_noload, L_eff_peak, b_peak
```

这个逻辑体现了工程取向：不是算出一个刚好满足目标电感的匝数就结束，而是继续检查峰值磁通是否越界。

### 8.6 绕线选择和窗口填充率

铜面积按电流密度估算：

```python
a_cu_mm2 = op.iin_rms / spec.J_max
```

默认 `J_max = 6 A/mm2`。

程序尝试标准线径：

```python
std_diameters = [0.8, 1.0, 1.2, 1.5, 1.8, 2.0]
```

对每个线径计算需要并绕根数：

```python
n_par = ceil(a_cu_mm2 / a_wire)
```

只要并绕根数不超过 4，就接受。

窗口填充率：

```python
kw = (pi * (wire_d_mm/2)^2 * n_parallel * n_turns) / Aw
```

寻优阶段要求：

```text
kw < 60%
```

如果超过，会在 `constraints` 字段中记录：

```text
kw=82%>60%
```

## 9. 电感损耗：铁损和铜损如何计算

`InductorLoss.compute()` 输出一个 `LossResult`：

```python
sub_losses = {
    "core": p_fe,
    "copper": p_cu
}
```

### 9.1 磁芯损耗

在 `InductorLoss._core_loss()` 中，先计算线峰值附近的纹波电流：

```python
vac_peak = op.vm
d_peak = 1.0 - vac_peak / spec.vout
delta_i = vac_peak * d_peak / (L_eff * fsw)
```

然后计算 AC 磁通半幅：

```python
Bac = L_eff * (delta_i / 2) / (N * Ae_total)
```

Steinmetz 系数从 `data/steinmetz_coefficients.json` 加载。查找顺序是：

```python
st = db.get_steinmetz(core.material)
if st is None:
    st = db.get_steinmetz(core.material_class)
```

当前实际调用的是 OSE：

```python
P_core = st.core_loss(spec.fsw, b_ac, ve_m3, method='ose')
```

也就是：

```text
Pv = k * f^alpha * B^beta
P_core = Pv * Ve
```

如果没有 Steinmetz 系数，则回退到 Mathcad 经验公式。

### 9.2 铜损

铜损路径：

```python
total_length_m = n_turns * core.mlt_cm / 100
rho = rho_cu(t_winding)
rdc = rho * length / area
```

绕组温度目前估算为：

```python
t_winding = spec.t_ambient + 40
```

集肤深度：

```python
delta = skin_depth(spec.fsw, t_winding)
```

集肤系数：

```python
f_skin = skin_effect_factor(d_wire_m, delta)
```

邻近效应当前按磁环分布式绕组处理，估算为 1 层：

```python
n_layers_est = 1
f_prox = proximity_factor(n_layers_est, d_wire_m, delta)
```

RMS 电流加入纹波修正：

```python
i_rms_total = op.iin_rms * sqrt(1 + (ripple_ratio / 3)^2)
```

铜损：

```python
P_copper = i_rms_total^2 * rdc * f_skin * f_prox
```

## 10. MOSFET 数据库和默认 Si 策略

MOSFET 数据库位于 `data/mosfets.json`，每个器件包含：

```text
manufacturer
part_number
technology
vds_max
id_25c
id_100c
rds_on_25c
rds_on_150c
rds_alpha
qg_nc
coss_er_pF
tr_ns
tf_ns
vgs
package
price_usd
```

`MosfetSpec` 中还有几个单位换算属性：

```python
qg = qg_nc * 1e-9
coss_er = coss_er_pF * 1e-12
tr = tr_ns * 1e-9
tf = tf_ns * 1e-9
```

默认查询：

```python
mdb.query(vds_min=spec.vout * 1.25, technology="Si")
```

`technology="Si"` 在实现中不是简单字符串匹配，而是一个特殊逻辑：

```python
if tech == "si":
    if not m_tech.startswith("si ") or m_tech == "sic":
        continue
```

所以它会选：

```text
Si CoolMOS
Si SuperJunction
```

不会选：

```text
SiC
GaN
```

这是本次修改后的一个重要行为：默认寻优是硅 MOSFET 基准方案。

## 11. MOSFET 损耗模型

`MosfetLoss` 位于 `models/mosfet.py`。

入口：

```python
MosfetLoss.compute(spec, op, mosfet, t_j=80.0)
```

默认结温使用 80 摄氏度。

### 11.1 温度修正后的 Rds_on

```python
rds_tj = rds_25 * (1 + rds_alpha * (t_j - 25))
```

### 11.2 导通损耗

MOSFET 在 Boost PFC 中按占空比导通，RMS 电流为：

```python
i_ds_rms = op.rms(op.iin_t, op.duty_t)
```

导通损耗：

```python
P_cond = i_ds_rms^2 * rds_tj
```

### 11.3 开关损耗

程序使用半周期平均开通电流：

```python
i_avg_on = 2 / pi * op.iin_peak
```

开通和关断能量：

```python
Eon = 0.5 * Vout * Iavg * tr
Eoff = 0.5 * Vout * Iavg * tf
```

开关损耗：

```python
P_sw = fsw * (Eon + Eoff)
```

### 11.4 Coss 损耗

```python
Eoss = 0.5 * Coss_er * Vout^2
P_coss = Eoss * fsw
```

### 11.5 栅极驱动损耗

```python
P_gate = Qg * Vgs * fsw
```

最终输出：

```python
sub_losses = {
    "conduction": p_cond,
    "switching": p_sw,
    "Coss": p_coss,
    "gate_drive": p_gate
}
```

这些字段会被 sweep 记录成：

```text
P_mosfet_cond_W
P_mosfet_sw_W
P_mosfet_coss_W
P_mosfet_gate_W
P_mosfet_W
```

## 12. 二极管、整流桥、电容模型

### 12.1 Boost 二极管

二极管模型位于 `models/diode.py`。

二极管在 MOSFET 关断时导通：

```python
diode_duty = 1.0 - op.duty_t
i_d_rms = op.rms(op.iin_t, diode_duty)
i_d_avg = op.avg(op.iin_t, diode_duty)
```

正向损耗：

```python
P_forward = diode_vf * i_d_avg + diode_rd * i_d_rms^2
```

反向恢复：

```python
if diode_type.upper() == "SIC":
    P_rr = 0
else:
    P_rr = Qrr * Vout * fsw
```

当前默认 `diode_type = "SiC"`，所以反向恢复损耗为 0。

### 12.2 输入整流桥

整流桥模型位于 `models/bridge_rectifier.py`。

工频整流桥按两颗二极管同时导通估算：

```python
i_in_avg = 2 * sqrt(2) / pi * op.iin_rms
P_bridge = 2 * bridge_vf * i_in_avg
```

注意整流桥是系统共享器件，所以系统汇总时不乘以相数。

### 12.3 输出电容

输出电容模型位于 `models/capacitor.py`。

低频纹波：

```python
delta_v_lf = Pout_per_phase / (2 * pi * f_line * C_total * Vout)
```

开关纹波估算：

```python
delta_i_sw = ripple_ratio * op.iin_peak
delta_v_sw = delta_i_sw / (8 * fsw * C_total)
```

RMS 纹波电流：

```python
ratio = (16 * Vout) / (3 * pi * Vm) - 1
Ic_rms = Iout * sqrt(ratio)
```

ESR 损耗：

```python
P_cap = Ic_rms^2 * ESR_total
```

还会估算寿命：

```python
L = L_rated * 2^((T_rated - T_core) / 10)
```

如果纹波电流超过额定值，还会叠加电流降额。

## 13. 寻优器的实际实现

寻优器位于 `optimization/sweep.py`。

核心函数：

```python
ParamSweep.sweep(base_spec, sweep_vars, n_cores=2, cores=None, mosfets=None)
```

这个寻优器背后的工程思想很直接：把过去工程师在 Mathcad/Excel 里手动改变的一组参数，全部变成数组；把过去靠经验记在脑子里的筛选条件，变成显式约束；把过去人工比较的几个候选点，扩展成上千个可复盘的设计组合。

例如传统做法可能是：

```text
先试 65 kHz
再试两个纹波比
换两颗常用 MOSFET
磁芯围绕历史方案微调
如果损耗差不多，就选一个熟悉的组合
```

这个流程效率很高，但覆盖空间有限，而且路径强依赖工程师个人习惯。当前软件的做法是：

```text
把 fsw 变成数组
把 ripple_ratio 变成数组
把磁芯数据库变成候选集合
把 MOSFET 数据库变成候选集合
对每个组合完整计算系统损耗
用同一组约束筛选
用同一个目标函数排序
```

这样得到的不是“某个工程师刚好想到的几个点”，而是“在当前数据库和约束下被系统枚举过的最佳点”。这就是自动寻优的实际价值。

### 13.1 笛卡尔积扫描

扫描变量：

```python
keys = list(sweep_vars.keys())
values = list(sweep_vars.values())
for combo in itertools.product(*values):
    params = dict(zip(keys, combo))
```

每个组合都会复制一份 `DesignSpec`：

```python
spec = DesignSpec(**{k: v for k, v in base_spec.__dict__.items()
                     if not k.startswith('_')})
```

再覆盖扫描参数：

```python
spec.fsw = float(params["fsw"])
spec.ripple_ratio = float(params["ripple_ratio"])
```

选择磁芯：

```python
core_idx = int(params.get("core_idx", 0))
core = cores[core_idx % len(cores)]
```

选择 MOSFET：

```python
mos_idx = int(params.get("mosfet_idx", 0))
mosfet = mosfets[mos_idx % len(mosfets)]
```

然后调用同一个系统分析器：

```python
op = compute_mathcad_operating_point(spec)
result = self.analyzer.analyze(
    spec, op, preferred_core=core, mosfet=mosfet, n_cores=n_cores
)
```

### 13.2 可行性约束

每个组合计算完后，程序检查三类约束。

第一，磁通密度：

```python
if b_max > core.bs_T * 0.7:
    feasible = False
    constraints.append(f"Bmax={b_max:.3f}T>{core.bs_T*0.7:.3f}T")
```

第二，窗口填充率：

```python
if design.kw > 0.6:
    feasible = False
    constraints.append(f"kw={design.kw:.0%}>60%")
```

第三，DC bias 后电感不能严重衰减：

```python
sat_pct = L_eff / L_noload * 100
if sat_pct < 20:
    feasible = False
    constraints.append(f"sat={sat_pct:.0f}%<20%")
```

这些约束失败原因会保存在 `constraints` 字段中。如果没有任何可行点，CLI 会统计最常见的失败原因，帮助判断应该扩大磁芯、提高纹波比，还是放宽某些设计边界。

### 13.3 结果表字段

每个扫描点最终会变成 DataFrame 的一行。核心字段包括：

```text
fsw_kHz
ripple_ratio
core
core_material
mosfet
mosfet_tech
mosfet_Rds25
turns
wire_d_mm
n_parallel
L_target_uH
L_noload_uH
L_eff_uH
B_max_T
sat_pct
kw
P_ind_core_W
P_ind_copper_W
P_ind_W
P_mosfet_cond_W
P_mosfet_sw_W
P_mosfet_coss_W
P_mosfet_gate_W
P_mosfet_W
P_diode_fwd_W
P_diode_rr_W
P_diode_W
P_bridge_W
P_cap_W
P_total_W
efficiency_pct
feasible
constraints
```

这些字段的价值是：不只是能排序，还能解释排序结果。

比如两个方案 `P_total_W` 相近，但一个方案 `kw=58%`、另一个 `kw=35%`，实际工程上第二个可能更容易绕线。再比如一个方案总损耗低，但 `Bmax` 已经非常接近上限，也需要谨慎看待磁芯温升和批量偏差。

### 13.4 排序逻辑

CLI 中最终排序：

```python
feasible = df[df["feasible"]]
top_n = feasible.nsmallest(top, "P_total_W")
```

也就是说，只有先满足约束的点，才有资格按系统总损耗排序。

## 14. 默认 Si MOSFET 寻优示例

命令：

```powershell
cd C:\Users\yangs\py
py -3 -m pfc_design optimize --fsw 65 --ripple-start 0.3 --ripple-stop 1.0 --ripple-n 8 --core-limit 10 --top 10
```

含义：

```text
固定 fsw = 65 kHz
纹波比从 0.3 到 1.0，取 8 个点
磁芯候选取 10 个 Sendust
MOSFET 默认只用 Si
显示总损耗最低的前 10 个可行点
```

实际扫描规模：

```text
Cores: 10 (Sendust)
MOSFETs: 13 (Si)
Total points: 1040
Results: 1040 total, 52 feasible
```

当前默认 Si 搜索下，最佳点为：

```text
fsw=65kHz
ripple=0.90
eta=97.09%
Core: 0077084A7-26u (Kool Mu 26u)
MOSFET: IPW65R032M8 (Si SuperJunction, Rds=32mOhm)
N=40
L_eff=144uH
Bmax=0.548T
sat=73%
Wire: 1.2mm x4
kw=57.6%
```

损耗细分：

```text
P_total=213.0W
P_ind=22.9W
P_mos=25.9W
P_dio=36.3W
P_br=37.8W
P_cap=5.1W

Inductor: core=8.7W, copper=14.2W
MOSFET: cond=12.1W, sw=11.6W, Coss=2.1W, gate=0.1W
Diode: fwd=36.3W, rr=0.0W
```

从这个结果可以看出，系统损耗并不是 MOSFET 一项决定的。整流桥、Boost 二极管、电感铜损都占明显比例。换句话说，如果下一步只盯着 MOSFET Rds_on，收益可能有限；反而可能需要评估整流桥压降、Boost 二极管方案或电感绕组方案。

## 15. 和 `--tech all` 的区别

默认命令不写 `--tech`，等价于：

```powershell
--tech Si
```

如果写：

```powershell
--tech all
```

程序会把 SiC 和 GaN 也加入 MOSFET 候选列表。

这时最佳点可能变成宽禁带器件。例如之前全技术固定 65 kHz 扫描中，GaN 器件 `GS66516T` 因为较低导通和开关相关损耗，会给出更低的系统总损耗。但这不代表它一定是量产选择，因为还需要考虑：

```text
器件成本
驱动复杂度
封装散热
EMI 风险
供应链
可靠性验证
控制器和驱动电源匹配
```

因此软件默认用 Si，是为了先建立一个传统硅器件基准。工程师可以再用 `--tech all` 定量评估宽禁带器件带来的损耗收益是否值得。

## 16. 常用命令

### 16.1 安装

在项目目录执行：

```powershell
cd C:\Users\yangs\py\pfc_design
py -3 -m pip install -e .
```

然后回到父目录运行：

```powershell
cd C:\Users\yangs\py
```

### 16.2 单点计算

```powershell
py -3 -m pfc_design run --no-plot
```

指定参数：

```powershell
py -3 -m pfc_design run --vin 176 --vout 410 --pout 7100 --fsw 65000 --ripple 1.0 --n-cores 2 --no-plot
```

注意：`run --fsw` 的单位是 Hz。

### 16.3 固定频率寻优

```powershell
py -3 -m pfc_design optimize --fsw 65 --ripple-start 0.3 --ripple-stop 1.0 --ripple-n 8 --core-limit 10 --top 10
```

注意：`optimize --fsw` 的单位是 kHz。

### 16.4 保存 CSV

```powershell
py -3 -m pfc_design optimize --fsw 65 --ripple-start 0.3 --ripple-stop 1.0 --ripple-n 8 --core-limit 10 --top 10 --csv pfc_design\output\sweep_65k_si.csv
```

### 16.5 扫描开关频率

```powershell
py -3 -m pfc_design optimize --fsw-start 45 --fsw-stop 120 --fsw-step 10 --ripple-start 0.3 --ripple-stop 1.0 --ripple-n 8 --core-limit 10 --top 10 --csv pfc_design\output\sweep_full_si.csv
```

### 16.6 查看 MOSFET 数据库

默认只看 Si：

```powershell
py -3 -m pfc_design mosfets
```

查看所有技术：

```powershell
py -3 -m pfc_design mosfets --tech all
```

只看 SiC：

```powershell
py -3 -m pfc_design mosfets --tech SiC
```

### 16.7 查看磁芯数据库

```powershell
py -3 -m pfc_design cores --material Sendust
```

## 17. 如何根据结果继续设计

拿到 Best Design 后，不应该直接把它当成最终量产方案，而应该按下面路径复核。

第一，看 `P_total_W` 和 `efficiency_pct`。这是系统级排序依据。

第二，看 `B_max_T` 和 `sat_pct`。如果 Bmax 接近 `0.7*Bsat`，或者 sat_pct 较低，磁件余量要谨慎。

第三，看 `kw`。当前约束是 60%。即使小于 60%，实际绕线也要考虑线径、并绕、绝缘、绕线机能力和温升。

第四，看损耗构成。如果 `P_bridge_W` 和 `P_diode_W` 很大，继续优化 MOSFET 可能不是最高收益方向。

第五，看 MOSFET 损耗分解。如果 `P_mosfet_sw_W` 接近或超过导通损耗，降低 fsw 或选择更快器件可能有效。如果 `P_mosfet_cond_W` 占主导，Rds_on 和散热更关键。

第六，看 CSV 中排名靠前的多个点，不要只看第一名。工程设计通常要在效率、磁件可制造性、成本和余量之间选择一个更稳健的点。

## 18. 已验证内容

当前工程保留了 Mathcad 对照测试：

```powershell
py -3 -m pytest tests\verify_mathcad.py -q
```

当前测试结果：

```text
8 passed
```

测试覆盖的关键点包括：

```text
Iin_rms
Dmin
Iin_peak
目标电感 L_target
匝数范围
系统效率范围
总损耗范围
整流桥损耗
```

这些测试不能证明所有模型都绝对准确，但能保证当前 Python 实现没有偏离原 Mathcad 基准太远。

## 19. 当前实现的边界

这个工具是功率级设计计算工具，不是控制固件。

它不会生成：

```text
F280039C PWM 配置
ADC 采样配置
CLA 任务
ISR 控制代码
UCC28070A 外围电路
环路补偿参数
保护状态机
```

它也没有完整热网络模型。当前 MOSFET 默认结温用 80 摄氏度估算，电感绕组温度用环境温度加 40 摄氏度估算。这适合设计早期比较，但不能替代热仿真和实测。

此外，磁芯损耗当前使用 Steinmetz OSE，适合建立工程估算基准，但对 PFC 电感真实非正弦磁通波形，后续仍可增强为更细的波形积分模型。

## 20. 后续可以继续增强的方向

后续版本可以继续往几个方向发展：

1. 增加 MOSFET、二极管、磁芯和电容的热阻模型，把温升作为约束。
2. 增加 BOM 成本目标，做损耗和成本的 Pareto 前沿。
3. 增加同步整流或无桥 PFC 拓扑比较。
4. 对磁芯损耗加入更真实的 PFC 线周期波形积分。
5. 增加 EMI 相关指标，例如开关频率偏好、di/dt、dv/dt 估算。
6. 增加器件数据库字段，例如封装热阻、供应商、库存状态。
7. 生成更适合评审会的 PDF 报告。
8. 输出用于固件设计的参数建议，例如目标电感、纹波、电流峰值、采样量程。

## 21. 总结

这个工具的核心不是“把 Mathcad 换成 Python”这么简单。

传统 Mathcad/Excel 的优势，是公式透明、适合推导、适合工程师逐项检查；它的短板，是多维参数组合一多，搜索路径就会越来越依赖个人经验和手动迭代次数。这个软件的出发点，就是把这种经验驱动的局部迭代，升级为由程序执行的系统级寻优。

它真正做的是把 PFC 设计从单点计算变成一个可复盘的系统级搜索过程：

```text
输入规格
生成低线工况
计算每个候选组合
拆解器件损耗
检查磁通、窗口和饱和约束
筛出可行点
按系统总损耗排序
输出最佳设计和完整 CSV
```

它的价值也不在于替代工程师，而在于让工程师更快看到系统取舍：

```text
为什么这个点损耗最低？
它的限制来自磁芯、绕线、MOSFET、二极管还是整流桥？
默认 Si 方案做到什么水平？
如果换 SiC/GaN，损耗收益有多大？
下一轮硬件设计应该优先优化哪里？
```

这就是自动计算和系统损耗最小寻优真正应该提供的信息。

最终的价值取向可以概括成一句话：

```text
让工程经验定义规则，让程序穷举组合，让数据呈现取舍，让工程师做最终判断。
```
