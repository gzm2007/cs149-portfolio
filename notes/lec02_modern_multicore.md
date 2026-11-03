# Lecture 2 — A Modern Multi-Core Processor（现代多核处理器）

> 来源：`slides/02_multicore.pdf` / `transcripts/lec02.txt`（讲义文本抽取，已修正连字乱码）
> 本讲回答一个问题：**现代处理器是怎么做到"快"的？** 答案由三块拼成 —— 超标量（ILP）、SIMD、多核 + 多线程。三者叠加后就得到"现代多核芯片"的完整图像。

---

## 0. 复习：程序、处理器、内存（Lecture 1 的三句话）

| 概念 | 定义 |
|---|---|
| 程序 | 一串处理器指令（编译后就是 `ld / mul / add / st / jmp`） |
| 处理器 | 循环执行 fetch/decode → execute，每时钟一条指令（最朴素的版本） |
| 寄存器 + PC | 执行上下文（execution context），保存程序状态 |
| 内存 | 按字节寻址的线性数组（linear address space） |

朴素处理器：**1 条指令 / 时钟**。但指令之间的**数据依赖**往往不要求严格顺序，这就是一切并行性的入口。

---

## 1. 并行形式一：指令级并行（ILP）与超标量（Superscalar）

### 1.1 依赖图 = 并行性地图

```
程序                                依赖图
00 a = 2                             00   01
01 b = 4                               \  /
02 tmp2 = a + b        (6)              02      04
03 tmp3 = tmp2 + a     (8)             /  \      |
04 tmp4 = b + b        (8)           03   05     |
05 tmp5 = b * b        (16)          /      \    |
06 tmp6 = tmp2 + tmp4  (14)        06 ------ 07  |   ← 06 依赖 02 和 04
07 tmp7 = tmp5 + tmp6  (30)                    /
08 if (tmp3 > 7)                              08
09/10 print
```

图里没有边相连的指令彼此独立，**可以同时执行**。这就是 instruction-level parallelism（ILP）。

### 1.2 Superscalar processor

- 每时钟 **decode 并执行最多 2 条**指令。
- 依靠 **out-of-order control logic**：硬件在指令流中**自动**寻找独立指令，投到多个执行单元。
- 关键限制：**如果指令流里本身没有 ILP，超标量一点用都没有**。

> "respect program order" 的含义：乱序只发生在"执行"层面；结果必须与顺序执行完全一致（数据依赖、分支、异常）。所以乱序对程序员**不可见**（single-thread 语义不变）。

### 1.3 本讲贯穿全场的例子：`sinx`（Taylor 展开）

```c
void sinx(int N, int terms, float* x, float* y) {
  for (int i = 0; i < N; i++) {
    float value = x[i];
    float numer = x[i] * x[i] * x[i];
    int denom = 6;      // 3!
    int sign = -1;
    for (int j = 1; j <= terms; j++) {
      value += sign * numer / denom;   // ← 依赖上一轮的 value
      numer *= x[i] * x[i];            // ← 依赖上一轮的 numer
      denom *= (2*j+2)*(2*j+3);        // ← 依赖上一轮的 denom
      sign  *= -1;                     // ← 依赖上一轮的 sign
    }
    y[i] = value;
  }
}
```

**内层循环是一条长长的依赖链，几乎没有 ILP。** 超标量在这里吃不到任何好处 —— 这是后面必须引入 SIMD 和多核的根本原因。

### 1.4 前多核时代 vs 多核时代

| | 前多核时代（pre multi-core era） | 多核时代 |
|---|---|---|
| 晶体管花在哪 | 让**单条指令流**跑得更快：大 cache、更聪明的 out-of-order、更强分支预测、硬件预取 | 直接加更多的**核** |
| 结果 | 单线程性能逐年提升 | 单核变简单（可能慢 25%），但数量翻倍 |

**Idea #1（多核）**：`2 核 × 0.75 效率 = 1.5×` 的理论加速比 —— 但前提是程序能把工作切开。原始 `sinx` 是一个线程，在多核上只会**慢 25%**。

两种表达并行的方式：

```cpp
// (a) 显式线程：把 N 个元素切成两半
void parallel_sinx(int N, int terms, float* x, float* y) {
  my_args args{N/2, terms, x, y};
  std::thread t(my_thread_func, &args);
  sinx(N - args.N, terms, x + args.N, y + args.N);  // 主线程做另一半
  t.join();
}
```

```c
// (b) 声明式：forall 告诉编译器"迭代之间独立"
forall (int i from 0 to N) { ... y[i] = value; }
```

`forall` 的价值：它是**编译器的许可证** —— 有了它，编译器可以自动生成多线程代码，**也可以**自动生成向量指令。

---

## 2. 并行形式二：SIMD（单指令多数据）

### 2.1 Idea #2：把"管理指令流的成本"摊薄到很多 ALU 上

```
        Fetch/Decode          ← 只有 1 份控制逻辑
             │
   ┌────┬────┬────┬────┐
  ALU0 ALU1 ALU2 ALU3 ... ALU7   ← 8 份执行单元，同一条指令广播给所有 ALU
        Execution Context
```

- 标量程序：`ld r0 / mul r1,r0,r0 / ...` → 一次处理 1 个元素。
- 向量程序：`vloadps / vmulps / ...` → 一次处理 **8 个 float**（256-bit 寄存器）。

```c
#include <immintrin.h>
for (int i = 0; i < N; i += 8) {                    // 8-wide
  __m256 origx = _mm256_load_ps(&x[i]);
  __m256 value = origx;
  __m256 numer = _mm256_mul_ps(origx, _mm256_mul_ps(origx, origx));
  __m256 denom = _mm256_broadcast_ss(&three_fact);
  for (int j = 1; j <= terms; j++) {
    __m256 tmp = _mm256_div_ps(_mm256_mul_ps(_mm256_set1ps(sign), numer), denom);
    value = _mm256_add_ps(value, tmp);
    numer = _mm256_mul_ps(numer, _mm256_mul_ps(origx, origx));
    denom = _mm256_mul_ps(denom, _mm256_broadcast_ss((2*j+2)*(2*j+3)));
    sign *= -1;
  }
  _mm256_store_ps(&y[i], value);
}
```

**注意**：SIMD 完全没有解决 `sinx` 的依赖链问题 —— 它让 8 条**互相独立的依赖链**（8 个不同的 `i`）挤进同一条指令流，靠宽度换吞吐。这正是"数据并行"的本质。

### 2.2 代价：条件执行必须用 mask

8 个 lane 里如果有的走 `if`、有的走 `else`，硬件只能**两条路径都执行**，再把不需要的结果 mask 掉：

```
时间(时钟)  1  2  ...  8
          ALU1 ALU2 ... ALU8
lane 掩码   T    T   F   T   F   F   F   ...
                └─ 没在用 ─┘  ← 这些 ALU 在做无用功
```

- 最坏情况：**1/8 峰值性能**（8-wide SIMD 下）。
- 分支结束后立刻恢复全速（`resume unconditional code`）。

**Breakout 问题：能不能只用一条 `if` 制造最坏情况？**
> 答：单条 `if` 最多让 lane 分成两组，且两组代码都要执行，所以单条 `if` 的最坏是 **50%**（一半 lane 有效）。要真正逼近 1/8，需要 **3 层嵌套 `if`**（2³ = 8 条互不相同的路径），让 8 个 lane 各走一条。这是深刻的一课：**SIMD 的效率取决于"宽度内控制流是否一致"**。

### 2.3 术语

| 术语 | 含义 |
|---|---|
| **Coherent execution**（指令流一致 / coherent control flow） | 同一指令序列作用于很多数据元素 —— **SIMD 高效的必要条件** |
| **Divergent execution** | 缺乏上述一致性 |
| 重要提醒 | Coherent execution **不是**多核并行的必要条件 —— 每个核有自己的 fetch/decode，可以跑完全不同的指令流 |

### 2.4 Explicit SIMD vs Implicit SIMD

| | Explicit SIMD（CPU） | Implicit SIMD（GPU） |
|---|---|---|
| 谁向量化 | 编译器（程序员用 intrinsics / `forall` 语义 / 自动向量化） | **硬件**：binary 里是标量指令，N 个程序实例一起跑 |
| 证据 | 反汇编可见 `vmulps` / `vstoreps` | 反汇编只有标量指令 |
| 宽度 | AVX2 256-bit（8×fp32）、AVX-512 512-bit（16×fp32）、ARM Neon 128-bit（4×fp32） | 现代 GPU 8 ~ 32 |
| 风险 | 编译器不认识并行就不会向量化 | **divergence 更致命**：写得差可能只跑到 1/32 |

---

## 3. 三种并行形式总表（本讲第一个核心结论）

| 形式 | 在哪 | 谁发现并行 | 并行的单位 |
|---|---|---|---|
| **Superscalar** | 核内 | **硬件**（运行时自动） | 同一指令流内的独立指令（ILP） |
| **SIMD** | 核内 | 编译器（explicit）或硬件（implicit） | 同一指令 → 多条数据 lane |
| **Multi-core** | 核间 | **软件**（线程 API / `forall`） | 完全不同的指令流（TLP） |

三种可以**叠加**：

```
16 核 × 每核 8-wide SIMD = 128 个元素同时算
16 核 × 4 硬件线程 × 8 lane = 512 个独立工作项才能把机器喂饱
```

---

## 4. 存储层次：cache 与延迟

### 4.1 抽象与现实

- 程序员看到的是**线性字节地址空间**；"load 地址 X 到 R0"这一条指令，实际可能涉及多级 cache 查找 + 访问 DRAM。
- **Cache 是实现细节**：不影响程序输出，只影响性能。
- Cache 以 **cache line** 为粒度工作（典型 64B）。

两种局部性（locality）：

- **空间局部性（spatial）**：读一个地址，把整条 line 载入，后续访问同一条 line 的其他地址就直接命中。
- **时间局部性（temporal）**：重复访问同一地址命中。

### 4.2 手算例题（讲义原题，务必会做）

设定：16 字节数组；cache 容量 **8 字节**；cache line **4 字节**（所以只能装 **2 条 line**）；**LRU** 替换。

访问序列：`0x0, 0x1, ..., 0xF`，然后**再来一遍** `0x0, 0x1, ...`

| 访问 | 动作 | 说明 |
|---|---|---|
| 0x0 | **cold miss**，载入 line 0x0 | 第一次访问必 miss |
| 0x1, 0x2, 0x3 | hit | 空间局部性 |
| 0x4 | cold miss，载入 line 0x4 | |
| 0x5, 0x6, 0x7 | hit | |
| 0x8 | cold miss，**evict line 0x0** | 只有 2 条 line，LRU 淘汰最久未用 |
| 0x9, 0xA, 0xB | hit | |
| 0xC | cold miss，**evict line 0x4** | |
| 0xD, 0xE, 0xF | hit | |
| **0x0（第二遍）** | **capacity miss**，evict line 0x8 | ⚠️ 不是 cold miss！数据曾经在 cache 里，是被**挤出去**的 |

**讨论题答案**
1. *为什么第二遍读 0x0 不命中？* 数组共 4 条 line，cache 只装 2 条 → 工作集大于容量。这叫 **capacity miss**。
2. *第二遍读 0x4 呢？* 同样 miss（在第 0xC 步已被淘汰）。
3. *如果 cache 有 4 条 line？* 第一遍之后整个数组都在 cache 里，第二遍**全命中**，只剩第一遍的 cold miss。

### 4.3 各级延迟（Kaby Lake，4 GHz）

| 数据在哪 | 延迟（周期） |
|---|---|
| L1 cache（32 KB） | **4** |
| L2 cache（256 KB） | **12** |
| L3 cache（8–20 MB） | **38** |
| DRAM（64 GB，最好情况） | **~248** |

一次 DRAM 访问 ≈ **250 个周期的空转**。若每时钟都能取指执行，这期间处理器本可以做完 250 条指令。

### 4.4 两种"掩盖延迟"的手段（都有限）

- **预取（prefetching）**：硬件猜你接下来要访问什么，提前载入 cache。
  代价：猜错会**浪费带宽并污染 cache**。
- 但如果是 `int x = some_function(); int y = A[x];` —— 地址**不可预测**（pointer chasing），cache 和预取都救不了你。这就是下一条 Idea 的动机。

---

## 5. 并行形式三：硬件多线程（Idea #3：用别的线程填满 stall）

> 类比：洗衣服时（洗衣机在转 40 分钟）去切菜，而不是站着等。

**核心思想**：一个硬件线程 stall 了（等内存），就从**另一个硬件线程**取指令执行。**ALU 数量不变**，只是把它们在时间上填满。

### 5.1 利用率手算（讲义原题）

模型：每个线程执行 **3 条算术指令 + 1 条 load（12 周期延迟）**；单发射核，每时钟最多 1 条指令。

```
1 个线程:  [3条算术][------ 12 周期 stall ------]  周期 0 ─ 15
利用率 = 3/15 = 20%

2 个线程:  交错后 = 6/15 = 40%
5 个线程:  交错后 = 15/15 = 100%   ← 需要 5 个才能打满
再多的线程（6,7,8...）无收益（已经 100%）
```

**换一个程序**：每线程 **6 条算术 + 1 条 load（12 周期）**
```
周期 = 6 + 12 = 18，每线程贡献 6 → ceil(18/6) = 3 个线程即 100%
```

### 5.2 两条 takeaway

1. 多线程**不会降低内存延迟**，它只是让长延迟**不再降低处理器利用率**。
2. **每访存的算术指令越多，隐藏延迟所需的线程越少**（算术密度 arithmetic intensity ↑ ⇒ 需要的并发度 ↓）。这条直觉在第 3 讲会升级成 **B(F)：bandwidth vs latency** 的形式。

### 5.3 多线程的两种实现

| | Interleaved multi-threading（temporal） | Simultaneous multi-threading（SMT） |
|---|---|---|
| 每时钟 | 从**一个**线程取一条指令 | 从**多个**线程各取指令，同时发射 |
| 例子 | 讲义主线 | Intel Hyper-Threading（2 threads/core） |

### 5.4 没有免费午餐：寄存器/cache 是有限资源

执行上下文的存储 = 有限的片上资源。存在一个**取舍**：

```
16 个"小"上下文          4 个"大"上下文
（每线程工作集小）        （每线程工作集大）
隐藏延迟能力强           隐藏延迟能力弱
但寄存器溢出 / 局部性差    但 cache 友好
```

硬件多线程本身**不增加** ALU 数量，它只是让 ALU 在长延迟操作面前更"忙"。

---

## 6. 真实机器长什么样

### 6.1 Intel Skylake / Kaby Lake 核（讲义解剖图）

- **2 路多线程**（2 execution contexts）
- 每核每时钟最多 **4 条独立标量指令** + **3 条 8-wide 向量指令**（2 条 vector mul 或 3 条 vector add）
- 3 个 8-wide AVX 单元（另有标量 ALU、LD/ST 单元未画出）

**i7-7700K（4 核）的算力估算**：

```
4 核 × 3 个 8-wide 单元 × 8 lane × 4.2 GHz ≈ 400 GFLOP/s
```

（讲义原式 `4 cores × 8-wide SIMD × 3 × 4.2 GHz = 400 GFLOPs`。注意计 flop 的口径：若把 FMA 的乘+加算作 2 次浮点运算，数字会翻倍 —— 考试里跟讲授义口径即可。）

### 6.2 NVIDIA V100 —— 吞吐导向的极端形态

单个 SM（Streaming Multiprocessor）：

| 资源 | 数量 |
|---|---|
| SIMD ALU | 128（16-wide fp32 单元，32-wide 操作需要 2 个时钟完成） |
| warp（执行上下文） | 每 SM **64 个** warp |
| 每 warp lane | 32 |
| 寄存器 | 256 KB / SM（64 warp 分摊） |
| 共享内存 + L1 | 128 KB |
| 时钟 | 1.6 GHz |

**关键算术**：

```
单 SM 并发数据项 = 64 warp × 32 lane = 2048
全芯片           = 80 SM × 2048 = 163,840 个数据项并发
算力             = 80 × 128 ALU × 1.6 GHz ≈ 16 TFLOP/s（约 250 W）
内存             = HBM2, 16 GB, 900 GB/s, 4096-bit 接口；L2 6 MB
```

这就是 **GPU "SIMT"**：binary 是标量指令，硬件把多个 warp 中**指令相同**的那些 lane 合并到 SIMD ALU 上并行；指令不同的 warp 的 lane 被 **mask 掉**（divergence）。

### 6.3 完整图景（Bonus slides 的要点）

把理解拆成 5 级台阶，能依次说出下面每个的差别，Lecture 2 就懂了：

```
① 单核单线程、1 指令/时钟        （最朴素）
② 超标量：同时发射多条独立标量指令（ILP，硬件发现）
③ + SIMD：向量寄存器 + 8-wide ALU，一条指令打 8 个数据
④ + 多线程：多个 execution context，交错填 stall
⑤ + 多核：多个 ④ 复制成一份芯片共享 cache/DRAM
```

---

## 7. 本讲结论：想跑满现代处理器，程序必须满足三条

1. **有足够多的并行工作**填满所有执行单元（跨核、跨核内单元）。
2. **成组的并行工作必须执行相同的指令序列**（才能吃到 SIMD）。
3. **暴露的并行工作数要多于 ALU 数量**，以便交错执行来隐藏内存 stall。

### 思考题（留给 Lecture 3）

> 任务：对两个长度为百万级元素的向量做逐元素乘 `C[i] = A[i] * B[i]`。
> 这是适合现代吞吐导向处理器的应用吗？

**提示**：每个元素要做 2 次 load + 1 次 mul + 1 次 store。三条要求里**第 1、2 条显然满足**（数据并行、控制流完全一致），第 3 条也满足。于是问题变成：算术只有 1 次乘法，却要搬 12 字节数据 —— **算术密度极低**。答案取决于机器是 **带宽受限（bandwidth-bound）** 还是 **延迟受限**，这就是第 3 讲 "latency vs bandwidth" 的切入点。

---

## 8. 术语表（讲义明确要求掌握的）

| 英文 | 中文 | 一句话记忆 |
|---|---|---|
| Instruction stream | 指令流 | 一个线程/PC 对应的指令序列 |
| Superscalar / ILP | 超标量 / 指令级并行 | 同一指令流内并行执行独立指令，硬件自动发现 |
| SIMD execution | 单指令多数据 | 一条指令驱动多个 ALU |
| Coherent control flow | 控制流一致 | 宽内 lane 走同一段代码 —— SIMD 高效的必要条件 |
| Divergent execution | 发散执行 | 宽内 lane 走不同代码 → mask 掉，最坏 1/width |
| Multi-core processor | 多核处理器 | 多个核，每核独立取指 → TLP |
| Hardware multi-threading | 硬件多线程 | 多个 execution context 共享同一组 ALU，用于隐藏延迟 |
| Interleaved MT | 交错（时间）多线程 | 每时钟选一个线程发射 |
| Simultaneous MT (SMT) | 同时多线程 | 每时钟从多个线程同时发射 |
| Cache line | 缓存行 | cache 的工作粒度（典型 64B） |
| Spatial / temporal locality | 空间/时间局部性 | 邻近代答 + 重复访问 |
| Cold miss / capacity miss | 冷缺失 / 容量缺失 | 第一次访问 / 曾被淘汰 |
| Latency vs bandwidth | 延迟 vs 带宽 | 多久拿到一个 / 单位时间能拿多少 |

---

## 9. 自测题（先做，再看答案）

**Q1.** 一个 16-wide SIMD 处理器上跑下面代码，最坏吞吐利用率是多少？为什么？
```c
if (t > 0) { /* 20 条指令 */ } else { /* 20 条指令 */ }
```
<details><summary>答案</summary>

单条 `if` 只能把 lane 分成两组，两组代码都要执行：`t>0` 的 lane 走完 20 条后空转等 `t<=0` 的 lane 走完，反之亦然 → 有效指令 20 条，实际发射 40 条 → **50%**。若要逼近 1/16，要 4 层嵌套 `if` 让 16 个 lane 各走一条独立路径。
</details>

**Q2.** 4 核、每核 8-wide SIMD、每核 2 个硬件线程的芯片，要让所有执行上下文都"有事做"，理想情况下至少需要多少个独立工作项？
<details><summary>答案</summary>

4 × 8 lane × 2 线程 = **64**。（讲义里 "16 核 × 8 ALU × 4 线程 = 512" 是同一个算法的放大版。）
</details>

**Q3.** 每线程执行 **10 条算术 + 1 条访存（延迟 20 周期）**，单发射核。需要几个硬件线程达到 100% 利用率？
<details><summary>答案</summary>

周期 = 10 + 20 = 30；每线程贡献 10 → 需要 **3** 个（30/10 = 3）。
</details>

**Q4.** 为什么 `sinx` 的内层循环在超标量处理器上几乎拿不到加速？
<details><summary>答案</summary>

4 条语句全部以 `value/numer/denom/sign` 自更新，构成环状依赖链（loop-carried dependence），每轮迭代必须等上一轮算完 → 指令流内 **没有 ILP**，超标量的第二个发射槽永远填不满。解决办法是把并行性**跨 `i`** 取（SIMD / 多线程），而不是在 `j` 方向找。
</details>

**Q5.** 讲义里 cache 只有 2 条 line 而数组有 4 条 line。把数组改成 2 条 line（8 字节）大小、其它条件不变，第二遍访问还会有 miss 吗？
<details><summary>答案</summary>

不会（除第一遍的 cold miss 外全命中）。整个过程只有 2 条 line 在工作集里，正好装得下 → 这演示了 **cache 容量要 ≥ 工作集** 这条亘古不变的原则。
</details>

**Q6.** 判断题：硬件多线程能降低内存访问延迟。
<details><summary>答案</summary>

**错。** 延迟是完全一样的（每次 DRAM 访问还是 ~248 周期）。多线程做的是"在等待期间去跑别的线程"，提高的是**利用率/吞吐**，不是延迟。这是 Lecture 2 最重要的一句话。
</details>

**Q7.** 为什么说 "coherent execution 不是多核并行的必要条件，但它是 SIMD 高效的必要条件"？
<details><summary>答案</summary>

多核里每个核有自己的 fetch/decode，各线程可以说是 `if` 一分支、`else` 另一分支，互不干扰，效率不受影响。SIMD 是**共享一份控制逻辑**，lane 之间控制流不一致就只能串行化两条路径 + mask，带宽被浪费。
</details>

---

## 10. 与课程其余部分的衔接

| 后续位置 | 与本讲的联系 |
|---|---|
| **Lecture 3**（multi-core arch II + ISPC） | latency vs **bandwidth**、ISPC 的 `foreach`（就是本讲的 `forall` 落地版）、算术密度 |
| **Lecture 4/5/6** | 有了本讲的"并行 + 局部性 + 延迟隐藏"三件套，才能谈 work distribution、locality、contention |
| **Lecture 7**（GPU/CUDA） | 本讲的 implicit SIMD、warp、divergence 直接展开 |
| **Lecture 11/12**（cache coherence / consistency） | 本讲的 cache 层次在**多核**下的正确性问题 |
| **Assignment 1** | 在 4 核 CPU 上分析并行程序性能 —— 正好用上"利用率 / 加速比 / 并行开销"这套量化工具 |

---

### 附：阅读建议
- 幻灯片重点：p.8–30（ILP/超标量）、p.31–45（SIMD 与 mask）、p.46–62（cache 手算）、p.63–80（多线程与利用率）、p.81–100（Skylake / V100 解剖图）。
- 教材：H&P《Computer Architecture: A Quantitative Approach》第 1 章 + 第 2 章（ILP、SIMD、SMT 部分）。
