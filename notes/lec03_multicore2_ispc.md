# Lecture 3 — Multi-Core Architecture Part II: Latency/Bandwidth + Parallel Programming Abstractions（多核架构之二：带宽问题 + 并行编程抽象）

> 来源：`slides/03_multicore2-ispc.pdf` / `transcripts/lec03.txt`
> 本讲回答两个问题：**① 为什么"算得快"的机器可能被"数据喂不饱"拖垮？（带宽 vs 延迟）② 编程抽象（SPMD/ISPC）和它的实现（SIMD）是什么关系？** 前半场讲硬件瓶颈，后半场讲抽象与实现。

---

## 0. 复习 + 开场思想实验

### 0.1 上节课的三大吞吐量思想

- 多核执行（multi-core）
- SIMD 执行
- 硬件多线程（hardware multi-threading）

### 0.2 思想实验：向量逐元素乘法 C = A × B

```
对每个 i：
  load A[i], load B[i]      ← 2 次内存读
  计算 A[i] × B[i]          ← 1 次 MUL
  store C[i]                ← 1 次内存写
```

假设向量有数百万个元素。**这适合跑在现代吞吐量导向的并行处理器上吗？**

答案留到 §2：每做一次乘法要搬 12 字节数据，计算/访存比极差 → **带宽受限**。

### 0.3 NVIDIA V100 有多大算力

- 80 个 SM × 每 SM 64 个 fp32 ALU = **5120 个 ALU**
- L2 缓存 6 MB，HBM 显存 16 GB、**900 GB/s** 带宽（4096-bit 接口）

问题：每个时钟都要"喂饱"5120 个 ALU，数据从哪来？

---

## 1. 延迟（Latency）vs 带宽（Throughput/Bandwidth）

### 1.1 高速公路类比：SF → Stanford

| 概念 | 类比 | 数值 |
|---|---|---|
| 延迟 | 一辆车开完全程的时间 | 0.5 小时（100 km/h，~50 km） |
| 吞吐量 | 单位时间到达的车数 | 2 辆/小时（一条车道、前车到了才发下一辆） |

**提高吞吐量的三种办法（核心洞察）：**

1. **开快车**（缩短延迟）→ 4 辆/小时
2. **多修车道**（复制资源）→ 8 辆/小时
3. **把车距拉近**（流水线！不改变延迟、不复制资源，只是让资源始终忙起来）→ 100 辆/小时，甚至 400 辆/小时

> 第 3 种是本讲的灵魂：**流水线可以在延迟不变、资源不变的情况下大幅提高吞吐量。**

### 1.2 术语定义

- **Memory bandwidth**：内存系统向处理器提供数据的速率（如 20 GB/s）
- 关键区分：延迟是"一件东西多久到手"，带宽是"每秒能到手多少件"——两者独立。

### 1.3 洗衣房类比：复制资源 vs 流水线

单套设备：洗衣机 45 min + 烘干机 60 min + 折叠 15 min

- **延迟**：洗完一锅 = 2 小时；吞吐 = 0.5 锅/小时
- **办法一：复制资源**（两台洗衣机、两台烘干机、叫个朋友）→ 资源 ×2，吞吐 ×2（1 锅/小时），延迟不变
- **办法二：流水线**（一锅进烘干时下一锅进洗衣机）→ **资源不变**，吞吐升到 1 锅/小时

两种办法都提高吞吐，但成本不同——流水线更"免费"。

### 1.4 瓶颈由最窄的一段决定

两根管子相接：100 L/s + 50 L/s → 整体最大流量 = **50 L/s**（min）。
对应到计算机：执行单元再快，数据供给跟不上就没用。

---

## 2. 带宽受限执行（本讲第一个重点）

### 2.1 实验设置

程序：每个线程反复执行三条**相互依赖**的指令：

```
1. X = load 64 bytes
2. Y = add x + x
3. Z = add x + y
```

核心假设：
- 每时钟执行 **1 条数学运算**
- load 可以和数学运算并行发射（co-issue）
- 内存每时钟只送来 **8 字节**（64 B ÷ 8 = **每次 load 要 8 个时钟才传完**）
- 最多 **3 个未完成的 load 请求**（outstanding loads）
- 硬件线程足够多，能隐藏内存延迟

### 2.2 发生了什么

时间线上：add、add、发射 load、add、add、发射 load……当 3 个 load 都在途时 → **Stall！** 核心没活干，只能等内存。

### 2.3 结论：memory bandwidth-bound

- **指令完成速率由内存供数速率决定**（8 B/时钟 ÷ 每次 load 64 B → 每 8 个时钟最多完成 1 次 load，即约 2~3 add/时钟的上限，再快就断粮）
- 内存 100% 时间在传数据，已经没有潜力可挖
- **红区（stall）是常态**：核在等数据

> ⭐ 重要论断（自测题）：稳态下核的利用率**只由指令吞吐和内存吞吐决定**，**与内存延迟和未完成请求数无关**（前提是线程多到能一直填满 pipeline）。

### 2.4 高带宽内存

现代 GPU 把高带宽内存放在处理器旁边：V100 用 **HBM2，900 GB/s**。

### 2.5 回到思想实验：算一笔账

C = A × B：每 1 次 MUL 配 **3 次内存操作 = 12 字节**。

- V100：5120 MUL/时钟 × 1.6 GHz × 12 B ≈ 需要 **~98 TB/s** 带宽
- 实际只有 900 GB/s → **GPU 效率 < 1%**
- 但 8 核 CPU（3.2 GHz Xeon，76 GB/s 内存总线）在这个计算上效率也只有 **~3%** —— GPU 仍然快得多，只是远没发挥满

### 2.6 本讲最重要的结论之一

> **这个计算是带宽受限的！** 克服带宽限制往往是面向现代吞吐量系统的开发者面临的**最首要挑战**。

高性能并行程序的做法：

1. **组织计算，减少访存**：
   - 复用本线程已加载的数据（**时间局部性**优化）
   - 线程间共享数据（inter-thread cooperation）
2. **宁可多做算术，也不要 store 再 load**（数学几乎是"免费"的）
3. 主旨：**程序必须少访问内存，才能高效利用现代处理器。**

### 2.7 澄清一个常见误解：指令流水线

"一个核每时钟做一次乘法"指的是**吞吐量**，不是延迟！

四段流水线：IF → D → EX → WB

- 单条指令延迟 = **4 周期**
- 吞吐量 = **每周期 1 条指令**
- （背靠背依赖指令需要处理正确性；真实流水线可变长，现代 CPU 可深达 ~20 级）

---

## 3. Part 2 主题：抽象 vs 实现（Abstraction vs Implementation）

> 全课程后半段的核心思维框架：**把"语义"和"实现/调度"分开，混淆二者是本课程困惑的常见根源。**

| | 语义（Semantics） | 实现（Implementation / Scheduling） |
|---|---|---|
| 问的问题 | 这个编程模型提供的操作**是什么意思**？给定程序，算出的**答案**是什么？ | 答案**如何**在并行机器上算出来？操作以什么（可能并行的）顺序执行？哪个线程/执行单元/向量 lane 算哪一步？ |
| 学生的目标 | 理解程序含义 | 能在脑中"追踪"并行机器每一步在做什么 |

---

## 4. ISPC：SPMD 编程模型

### 4.1 什么是 ISPC

- **Intel SPMD Program Compiler**，SPMD = Single Program Multiple Data
- 推荐读物：Matt Pharr 的 *The Story of ISPC*（ispc.github.com / pharr.org 博客）

### 4.2 例子：sinx 的 ISPC 版

调用端（C++）不变，只是 `ispc_sinx()` 编译成了另一个世界：

```c
export void ispc_sinx(uniform int N, uniform int terms,
                      uniform float* x, uniform float* result)
{
    // assume N % programCount = 0
    for (uniform int i = 0; i < N; i += programCount)
    {
        int idx = i + programIndex;
        float value = x[idx];               // 蓝色变量：每个实例一份
        ...
        uniform int denom = 6;              // uniform：全 gang 一份
        uniform int sign = -1;
        for (uniform int j = 1; j <= terms; j++) { ... }
        result[idx] = value;
    }
}
```

**SPMD 抽象的语义：**
- 调用 ISPC 函数 → 生成一个 **gang**，含 `programCount` 个**程序实例（program instances）**
- 所有实例**并发运行同一份代码**，各自有局部变量的私有副本
- 函数返回时 → 所有实例都已完成，回到 C++ 的单线程顺序执行

**关键字：**

| 关键字 | 含义 |
|---|---|
| `programCount` | gang 中同时执行的实例数（uniform 值） |
| `programIndex` | 当前实例在 gang 中的编号（varying，每个实例不同） |
| `uniform` | 类型修饰符：所有实例的该变量值相同；**纯优化用途，不影响正确性** |
| `export` | 可从 C++ 调用的 ISPC 函数 |

### 4.3 两种把数组元素分给实例的写法（重要！）

**版本 1：Interleaved（交错分配）** `idx = i + programIndex;`（i 每次 += programCount）

```
实例:    0  1  2  3  4  5  6  7 | 0  1  2  3 ...
元素:    0  1  2  3  4  5  6  7 | 8  9 10 11 ...
```

→ 8 个实例读的元素**内存连续** → 一条 packed vector load（`vmovaps` / `_mm256_load_ps`）高效搞定。✅

**版本 2：Blocked（块分配）** `idx = start + i;`（start = programIndex * count）

```
实例:    0  1  2  3  4  5  6  7 | 0  1  2 ...
元素:    0  8 16 24 32 40 48 56 | 1  9 17 ...
```

→ 一次 load 要取 **8 个不连续**的值 → 需要 **gather 指令**（`vgatherdps`），更复杂、更贵。❌

> 调度方式是**实现细节**，但对性能影响巨大——这正是"抽象 vs 实现"的第一课。

### 4.4 ISPC 如何实现 gang

- gang 的实例数 = 硬件 SIMD 宽度（或其小倍数）
- ISPC 编译器生成含 SIMD 指令的 `.o` 文件，C++ 正常链接
- **gang 抽象 = SPMD 语义；SIMD 指令 = 实现**

### 4.5 `foreach`：更高的抽象层次

```c
foreach (i = 0 ... N) {
    float value = x[i];   // i 是 varying 的：每个实例一个 i
    ...
}
```

- 程序员只声明：**整个 gang 要完成 0..N 这些迭代**
- ISPC 负责**把迭代分配给实例**——不再手写 `programIndex`
- 好处：程序看起来几乎像顺序程序（"对输入数组里每个元素独立地……"）

**foreach 的四种可能实现（理解"抽象允许多种实现"）：**

1. 实例 0 独自干完所有迭代（合法但慢）
2. 交错分配（interleave）
3. 块分配（block）
4. **动态分配**：`atomic_add_local(&nextIter, 1)` 抢迭代号（负载不均衡时好）

### 4.6 抽象的边界：ISPC 语义的坑

ISPC 是**低层语言**——它暴露 `programIndex/programCount`，所以：

**例 1（能写但输出未定义）：**

```c
foreach (i = 0 ... N) {
    if (i >= 1 && x[i] < 0)  y[i-1] = x[i];   // i 和 i-1 可能由
    else                       y[i]   = x[i];  // 不同实例同时写！
}
```
多个迭代可能写同一内存位置 → **输出未定义（undefined）**。

**例 2（依赖特定 gang 大小的高级协作）：**

8 个元素求积，用 `shift` + 按位归约，**lg(8) = 3 步**完成（树形归约）——写得出来，但正确性依赖 `programCount == 8`。

**例 3（求和的错误写法 → 编译错）：**

- `float sum; ... sum += x[i];` → varying 类型无法作为返回值给期望单值的 C++ ✗
- `uniform float sum; ... sum += x[i];` → 把 varying 值加进 uniform 变量，语义不明 ✗

**正确写法：私有部分和 + 跨实例归约**

```c
uniform float sum;
float partial = 0.0f;          // 每个实例私有累加，零通信
foreach (i = 0 ... N) partial += x[i];
sum = reduce_add(partial);     // 跨实例通信原语，返回 uniform
```

等价于手写 AVX intrinsics：向量累加 `_mm256_add_ps`，最后把 8 个 lane 水平求和。

**ISPC 跨实例操作（标准库）：**

| 原语 | 作用 |
|---|---|
| `reduce_add(x)` | gang 内所有实例求和 → uniform |
| `reduce_min(a)` | gang 内求最小 |
| `broadcast(v, idx)` | 把实例 idx 的值广播给所有实例 |
| `rotate(v, offset)` | 实例 i 拿到实例 (i+offset) % programCount 的值 |

### 4.7 ISPC tasks（多核维度）

- gang 是**一个核上一个线程里**的 SIMD —— 前面所有代码只用到了 4 核机器中的 1 个核！
- **task** 是 ISPC 的另一层抽象，用来获得**多核执行**（详见 assignment 1）

---

## 5. 抽象层级光谱（本讲的收尾升华）

| 层级 | 语言形态 | 程序员看到什么 |
|---|---|---|
| 低（现在的 ISPC） | 暴露 `programIndex/programCount` | 实例的存在：可写未定义程序、可写依赖 gang 大小的程序 |
| 中 | 假想 ISPC 去掉 `programIndex/programCount`，只剩 `foreach` | 只需想迭代；foreach 外全是 uniform 逻辑 |
| 高 | 连数组下标都不给：`y = map(doWork, x)` | 完全无循环、无索引——**NumPy / PyTorch 的世界**（如 `Z = X + Y`） |

> 抽象越高，能表达的协作模式越少，但越不容易出错、越容易被高效实现。这个光谱后面课程（数据并行、Spark、DSL）会反复出现。

---

## 6. 本课总结

1. **带宽是现代计算的关键资源**：算力增长远快于带宽增长；带宽受限的程序（如逐元素运算）在 GPU 上效率可以 <1%。
2. **延迟 ≠ 吞吐**：流水线和复制资源都能提吞吐；流水线"更免费"。稳态利用率只取决于指令/内存吞吐之比。
3. **抽象 vs 实现**是贯穿全课的思维方式：SPMD（gang、foreach）是语义，SIMD 指令、interleave/block/动态调度是实现。
4. **ISPC**：低层 SPMD 语言，暴露实例编号可以表达高级协作（树形归约、rotate），但也允许写出未定义行为；`uniform` 是优化提示；`reduce_add` 等是跨实例通信；`task` 补上多核维度。

### 自测清单

- [ ] 能解释为什么 C = A×B 在 V100 上效率 <1%，瓶颈公式怎么算？
- [ ] 能说明"稳态核利用率与内存延迟、未完成请求数无关"的论证？
- [ ] 能对比 interleaved 与 blocked 分配对应的 SIMD 指令（vmovaps vs vgatherdps）？
- [ ] 能说出 foreach 的 4 种实现，并解释哪种适合负载不均衡？
- [ ] 能解释 `sum_array` 正确版本为什么等价于 AVX 向量累加 + 水平求和？
