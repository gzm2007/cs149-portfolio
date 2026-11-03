# Lecture 4 — Parallel Programming Basics（并行编程基础）

> 来源：`slides/04_progbasics.pdf` / `transcripts/lec04.txt`
> 本讲是**如何写并行程序的案例研究**：用一个贯穿全场的 2D 网格求解器，演示两种编程模型——**数据并行（data parallel）**和**共享地址空间（shared address space）**——如何从零把一个顺序程序改造成并行程序。

---

## 0. 本讲主线

> 写并行程序的思考流程 = ① 找出可并行的工作 → ② 划分工作（和数据）→ ③ 管理数据访问、通信、同步。

用 §1~§4 的四个阶段（decomposition / assignment / orchestration / mapping）作为骨架，§5 起用网格求解器完整走一遍。

---

## 1. 创建并行程序的四个阶段（Culler/Singh/Gupta 框架）

```
问题 → 【Decomposition 分解】→ 子问题（tasks，"要做的工作"）
     → 【Assignment 分配】   → 并行线程（workers，"干活的人"）
     → 【Orchestration 编排】→ 并行程序（会通信的线程）
     → 【Mapping 映射】      → 在并行机器上执行
```

**这四个职责可以由程序员、系统（编译器/运行时/硬件）、或两者共同承担。**

### 速度是目标

```
Speedup(P) = Time(1 processor) / Time(P processors)
```

其他目标：高效率（成本/面积/功耗）、能解决单机放不下的更大问题。

### 1.1 Decomposition（分解）：找出依赖

- 把问题拆成可并行的 task；一般要**足够多的 task 让所有执行单元都忙起来**。
- ⭐ **分解的核心挑战：识别依赖（dependencies）——即识别"没有依赖"的地方。**
- 谁来做？**大多数情况是程序员。** 自动并行化仍是难题：
  - 编译器必须做依赖分析；如果是**数据相关**（运行时才知道）的依赖怎么办？
  - 研究者在简单循环嵌套上有些成果，但通用代码的"魔法并行化编译器"**尚未实现**。

### 1.2 Amdahl 定律：序列部分决定加速上限

设 S = 程序中**本质串行**（无法并行）的比例，则：

```
Max Speedup ≤ 1 / S
```

**图像例子**（N×N 图像，两步）：
- Step 1：所有像素亮度 ×2（完全独立）
- Step 2：求所有像素的平均值

| 版本 | 做法 | 时间 | 加速比 |
|---|---|---|---|
| 顺序 | 两步都串行 | 2N² | 1 |
| 第一版并行 | Step1 并行，Step2 串行 | N²/P + N² | ≤ 2 |
| 第二版并行 | Step1 并行；Step2 并行求部分和 + 串行合并 | N²/P + N²/P + P | → P（当 N ≫ P） |

- 第二版多出的 P 是**并行算法的开销（overhead）**：合并部分和。
- **Summit 超算**：27,648 GPU × 5,376 ALU = 1.48 亿 ALU；若应用有 **0.1% 串行**，最大加速比 = **1000**（1/S）——相对 1.48 亿的算力，这就是 Amdahl 的"小串行区域拖垮大机器"。

### 1.3 Assignment（分配）：task → worker

- worker 可能是：线程、程序实例、向量 lane……
- 目标：**负载均衡好、通信开销小**
- 时机：**静态**（运行前，如把数组前半给 t1、后半给主线程）或**动态**（运行时拉取）
- 责任：常由语言/运行时接管，也有程序员手写

**四种分配实例：**

| 方式 | 代码要点 | 特点 |
|---|---|---|
| ISPC interleaved（静态） | `idx = i + programIndex` | 程序员管理分配 |
| ISPC `foreach` | 系统管理；当前实现为静态 | 抽象上允许动态，实现是静态 |
| C++11 threads 静态 | `std::thread t1(...); 主线程算另一半` | 块分配，手写 |
| ISPC tasks 动态 | `launch[100] my_ispc_task(...)` | 运行时维护任务列表，worker 线程干完一个从列表取下一个，**下一个任务指针** |

### 1.4 Orchestration（编排）

包含：组织通信、加**同步**以保持依赖、组织数据结构内存布局、调度 task。

目标：降低通信/同步成本、保持数据局部性、减少开销。

> 机器细节影响这些决策：**如果同步很贵，程序员就会用得更稀疏（sparse）。**

### 1.5 Mapping（映射到硬件）

| 由谁映射 | 例子 |
|---|---|
| 操作系统 | 线程 → CPU 核上的硬件执行上下文 |
| 编译器 | ISPC 程序实例 → 向量指令 lane |
| 硬件 | CUDA 线程块 → GPU 核（后续课） |

关键权衡：
- **相关的线程放同一个核** → 最大化局部性、数据共享，降低通信/同步成本
- **不相关的线程放同一个核** → 一个带宽受限 + 一个算力受限 = 机器利用更充分

---

## 2. 贯穿案例：2D 网格偏微分方程（PDE）求解器

### 2.1 问题与算法

在 (N+2)×(N+2) 网格上求解 PDE，迭代算法：**Gauss-Seidel 扫描**直到收敛。

```c
A[i,j] = 0.2f * (A[i,j] + A[i,j-1] + A[i-1,j] + A[i,j+1] + A[i+1,j]);
```

顺序伪代码（外层 while 直到收敛；内层遍历非边界点）：
```c
while (!done) {
  diff = 0.f;
  for (i=1; i<n; i++)
    for (j=1; j<n; j++) {
      prev = A[i,j];
      A[i,j] = 0.2f * (A[i,j] + A[i,j-1] + A[i-1,j] + A[i,j+1] + A[i+1,j]);
      diff += fabs(A[i,j] - prev);
    }
  if (diff/(n*n) < TOLERANCE) done = true;
}
```

### 2.2 Step 1：找依赖（问题分解阶段）

- 每个元素依赖**左边的元素**（Gauss-Seidel 顺序更新导致的"前向"依赖）
- 每一行依赖**上一行**
- ⭐ **好消息：对角线之间存在独立工作！** 沿对角方向的"波前（wavefront）"可并行
- ❌ **坏消息：独立工作难以利用**：
  - 计算开始和结束时并行度很低（斜边小）
  - **每完成一条对角线就要同步一次** —— 同步太频繁

### 2.3 关键技巧：改算法，让工作"更并行"

> 思路：**为了并行重新排序网格单元的更新顺序**——换一种算法，收敛路径不同但最终解（在误差阈值内）相同。

- 是的，这需要**领域知识**（知道 Gauss-Seidel 这样改是合法的）——但这是并行编程的常用手法。

**红黑着色（red-black coloring）：**
```
① 并行更新所有红格
② 红格全部完成后，并行更新所有黑格（依赖红格的结果）
③ 重复直到收敛
```

→ 每个阶段内**全网格**可并行，只需**两个阶段之间的同步**（比沿对角线频繁同步好得多）。

### 2.4 分配方式影响通信量

- 问题：blocked 还是 interleaved 分配更好？**取决于所跑的系统。**
- 关键观察：**blocked 分配（块状划分）在处理器之间需要传输的数据更少**（边界小、局部性好）。

### 2.5 两种编程模型表达同一个程序

| | 数据并行（data parallel） | 共享地址空间 SPMD |
|---|---|---|
| 视角 | "对每个元素独立做 X"（for_all） | "每个线程干自己那部分，用全局变量通信" |
| 同步 | 隐式：forall 块结束处自动等待所有 worker | 显式：锁 + 屏障 |
| 通信 | load/store 隐式 + 内建原语（reduceAdd） | load/store 共享变量隐式 |

**数据并行版（只显示红格更新）：**
```c
for_all (red cells (i,j)) {
    float prev = A[i,j];
    A[i,j] = 0.2f * (A[i-1,j] + A[i,j-1] + A[i,j] + A[i+1,j] + A[i,j+1]);
    reduceAdd(diff, abs(A[i,j] - prev));   // 内建通信原语
}
// 离开 for_all 块 = 隐式等待所有 worker 完成
if (diff/(n*n) < TOLERANCE) done = true;
```
- Decomposition：单个网格元素就是独立工作（系统内建）
- Assignment：`???` —— 由系统负责
- Orchestration：系统负责（reduceAdd + 隐式屏障）

---

## 3. 共享地址空间模型（SPMD 线程）

### 3.1 模型本身：一块"公告板"

- 线程通过**读写共享地址空间中的变量**通信——**通信隐式地藏在 load/store 里**
- 共享地址空间像一个**公告板**：人人可读可写
- 这是顺序编程的自然延伸（本课之前所有讨论默认共享地址空间）

### 3.2 为什么需要互斥（mutual exclusion）？

`x++` 实际是三条指令：
```
r1 ← x      (load)
r1 ← r1 + r2 (add)
x  ← r1     (store)
```
两个线程交错执行时（x 初值 0，各 +1）：T1 读到 0、T2 也读到 0 → 都算成 1 → 最后 x = 1 而不是 2。**丢失更新（lost update）。**

→ **这三条指令必须"原子（atomic）"。**

### 3.3 保持原子性的机制

| 机制 | 形态 |
|---|---|
| 互斥锁 | `mylock.lock(); ...critical section...; mylock.unlock();` |
| 语言一等支持 | `atomic { ... }` 代码块 |
| 硬件原子读-改-写 intrinsic | `atomicAdd(x, 10);` |

### 3.4 网格求解器的 SPMD 版（完整伪代码）

```c
int n; bool done = false; float diff = 0.0;
LOCK myLock; BARRIER myBarrier;
float* A = allocate(n+2, n+2);

void solve(float* A) {
  int threadId = getThreadId();
  int myMin = 1 + (threadId * n / NUM_PROCESSORS);   // 块状分配
  int myMax = myMin + (n / NUM_PROCESSORS);

  while (!done) {
    float myDiff = 0.f;
    diff = 0.f;
    barrier(myBarrier, NUM_PROCESSORS);

    for (j = myMin to myMax)
      for (i = red cells in this row) {
        float prev = A[i,j];
        A[i,j] = 0.2f * (A[i-1,j] + A[i,j-1] + A[i,j] + A[i+1,j] + A[i,j+1]);
        myDiff += abs(A[i,j] - prev);        // 本线程私有累加（无锁）
      }

    lock(myLock);                            // ← 为什么有锁？
    diff += myDiff;                          //   因为 diff 是共享变量，
    unlock(myLock);                          //   多个线程 += 会丢失更新
    barrier(myBarrier, NUM_PROCESSORS);

    if (diff/(n*n) < TOLERANCE) done = true; // 所有线程看到同样的 done
    barrier(myBarrier, NUM_PROCESSORS);
  }
}
```

### 3.5 屏障（barrier）语义

- `barrier(num_threads)`
- **屏障把计算切成阶段（phases）**；是表达依赖的**保守（conservative）**方式：
  - 屏障**之前**所有线程的所有计算都完成，才允许**之后**任何线程的计算开始
  - 即：屏障后的一切都假定依赖屏障前的一切

### 3.6 三个坑：锁、屏障、开销（本讲最精彩的三问）

**Q1：为什么有锁？**
`diff += myDiff` 是 load-add-store 的读-改-写，多个线程并发会丢失更新 → 必须互斥。

**Q2：为什么有三个屏障？**
- 第一个：本轮 `diff=0.f` 清零必须在所有线程开始本轮累加**之前**完成（否则别的线程可能读到旧值/已累加的值）
- 第二个：所有线程的 `diff += myDiff` 完成后，才能安全读 `diff` 判断收敛
- 第三个：所有线程都看到 `done` 一致后，下一轮开始前同步（避免一个线程先进入下一轮把 diff 清零）

**Q3：性能问题在哪？**
- 锁虽然放在内层循环外（每线程每轮一次），但仍**每轮阻塞所有线程**（串行化）
- 更狠的优化：**用 `diff[3]` 三个副本 + index 轮转**，彻底消除相邻轮次之间的依赖 → **只留一个屏障**：

```c
float diff[3];  // 全局，但用3份
int index = 0;  // 线程本地
while (!done) {
  myDiff = 0.0f;
  // ...计算并本地累加...
  lock(myLock);
  diff[index] += myDiff;          // 原子更新当前这份
  unlock(myLock);
  diff[(index+1) % 3] = 0.0f;     // 清零下一份（与当前份无冲突）
  barrier(myBarrier, NUM_PROCESSORS);
  if (diff[index]/(n*n) < TOLERANCE) break;
  index = (index + 1) % 3;
}
```
> 手法：**用 3 份 diff 轮转，牺牲一点内存（footprint）换取消除相邻迭代间的依赖** —— 并行编程的常见技巧。

---

## 4. 两种编程模型的对比（总结表）

| | 数据并行 | 共享地址空间 |
|---|---|---|
| 同步 | 单逻辑控制流；forall 迭代可被系统并行；**forall 块末尾隐式屏障** | **显式互斥**（锁保护共享变量）+ **屏障**表达阶段依赖 |
| 通信 | load/store 隐式 + 内建原语（如 reduce） | load/store 共享变量隐式 |
| 程序员管什么 | 只写"对每个元素做什么" | 分配（threadId 算区间）、锁、屏障全手写 |

---

## 5. 本课总结

1. **Amdahl 定律**：整体加速比被**串行部分**限制（≤1/S）；小串行区域就能拖垮巨型机器。
2. **创建并行程序的四阶段**：decomposition → assignment → orchestration → mapping；责任可在程序员与系统间分配。
3. **今天的重点：识别依赖**——这是分解阶段的核心挑战，自动并行化仍很难。
4. **下一课重点：识别局部性、减少同步**（今天的网格求解器已经埋下伏笔：三屏障 → 一屏障、锁的开销、分配方式的通信成本）。

### 自测清单

- [ ] 用四阶段框架解释一个你熟悉的程序（如 MapReduce 词频统计）？
- [ ] 为什么 Summit 上 0.1% 串行就让加速比上限只有 1000？算一遍。
- [ ] 网格求解器为什么"沿对角线"能并行，却仍然不好用？（斜边小 + 每对角同步）
- [ ] 红黑着色为什么合法？需要什么领域知识？
- [ ] 三个屏障各自防的是什么？删掉任意一个会出什么错？
- [ ] `diff[3]` 轮转方案为什么能只用一个屏障？
- [ ] 数据并行 vs 共享地址空间，同步责任分别落在谁身上？
