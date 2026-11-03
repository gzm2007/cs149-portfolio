# CS149 并行计算学习记录

> 一个面向组队/交流的公开快照：课程笔记、性能测量数据、自己写的工具，以及一份完整的优化分析。
> 不包含 Stanford CS149 的课件、作业 handout 或作业解答。

**作者**：Ziming Guan

**In short** — I am working through Stanford CS149 (Fall 2023), focusing on multi-core
performance analysis, SIMD/ISPC, and the measurement discipline behind optimization.
This repository collects my notes, measurement tooling, and reproducible results.
Course materials and assignment solutions are intentionally not published.

---

## 1. 我在学什么

- **并行计算基础**：ILP / SIMD / 多核与硬件多线程；带宽 vs 延迟；数据并行与共享地址空间。
- **性能分析方法**：先测量再优化。关注每线程耗时、负载不均衡、内存带宽瓶颈，而不只是最终加速比。
- **SIMD 与 ISPC**：向量化、掩码（predicated execution）、SPMD 编程模型与任务系统。
- **异构 CPU 上的可复现测量**：P/E 核调度会让线程扩展曲线失真，因此自己写了绑核工具。
- 后续计划：CUDA、缓存一致性、锁与一致性模型。

工作环境是 Windows + MSYS2 UCRT64 + g++/ISPC。官方课程要求 Linux，本仓库记录了把 handout
移植到该环境所需的改动（见 [notes/environment.md](notes/environment.md)）。

## 2. 仓库结构

```
.
├── notes/
│   ├── lec02_modern_multicore.md      # 超标量、SIMD、多核：现代处理器如何变快
│   ├── lec03_multicore2_ispc.md       # 带宽/延迟、SPMD 与 ISPC
│   ├── lec04_progbasics.md            # 并行程序的四个阶段与网格求解器案例
│   ├── environment.md                 # Windows 工具链搭建、P/E 核拓扑、测量方法
│   └── tools/
│       ├── runon.cpp                  # 自写 CPU 绑核工具（替代 taskset）
│       ├── env.ps1                    # PowerShell 环境入口
│       ├── cmd.cmd                    # cmd 环境入口
│       └── msys2-shell.cmd            # MSYS2 UCRT64 shell 入口
└── assignments/asst1/
    ├── prog1_mandelbrot_threads/
    │   ├── results/                   # 两份完整报告、CSV、SVG 图表
    │   └── scripts/                   # 数据采集与绘图脚本
    ├── prog2_vecintrin/
    │   └── TASK.md                    # 向量化任务记录（实现进行中）
    └── prog6_kmeans/
        ├── gen_synthetic_data.cpp     # 本地合成数据集（非 handout）
        └── plot.py                    # 聚类结果可视化
```

> handout 源码不在本仓库中，因此 `scripts/` 与 `gen_synthetic_data.cpp` 不能直接编译运行；
> 它们保留在这里是为了说明测量流程和数据处理方式。原始运行日志也已剔除，只保留聚合后的 CSV 与图表。

## 3. 亮点：Program 1 — Mandelbrot 多线程优化

[完整对比报告](assignments/asst1/prog1_mandelbrot_threads/results/comparison_block_vs_interleaved.md) ·
[interleaved 详细报告](assignments/asst1/prog1_mandelbrot_threads/results/interleaved/report.md) ·
[block 详细报告](assignments/asst1/prog1_mandelbrot_threads/results/step3/report.md)

**问题**：把串行 Mandelbrot 渲染改成多线程。图像不同行的计算量差异很大——中间行迭代次数远多于上下边缘。

**过程**：

1. 先用**连续行块**划分，扩展曲线出现明显锯齿：3 线程只有 1.67x，8 线程 4.05x。
2. 用 `CycleTimer` 记录每线程忙时，发现 `Max/Mean` 长期在 1.8–2.0：最慢线程做了约两倍的平均工作。
3. 改成**交错行划分**（线程 `t` 处理第 `t, t+T, t+2T, ...` 行），每个线程拿到同样的行数和同样的“贵/便宜行”混合，无需同步。
4. 复测每线程耗时，`Max/Mean` 降到 1.00–1.03，**8 线程达到 7.61x（view 1）/ 7.20x（view 2）**。

| 线程数 | view 1 block | view 1 interleaved | view 2 block | view 2 interleaved |
|---:|---:|---:|---:|---:|
| 3 | 1.67x | **3.05x** | 2.22x | **2.98x** |
| 4 | 2.52x | **4.05x** | 2.62x | **4.00x** |
| 8 | 4.05x | **7.61x** | 4.19x | **7.20x** |

报告还分析了 16 线程为何只比 8 线程快 6–16%：16 个逻辑核中有 8 个 E 核、2 个低功耗 E 核，
而且此时 `Max/Mean` 的上升来自**核间性能差异**，不是划分不均。

## 4. 亮点：测量工具与环境工程

- **[runon.cpp](notes/tools/runon.cpp)**：Windows 没有 `taskset`。该工具以
  `CreateProcessW(..., CREATE_SUSPENDED)` 启动子进程，先 `SetProcessAffinityMask` 再
  `ResumeThread`，保证亲和性在第一条指令前生效。
- **用计时反推核拓扑**：官方 `EfficiencyClass` 在这台机器上的含义与直觉相反。最终用逐核运行
  mandelbrot 的耗时确认：P 核 ~216–223 ms，E 核 ~229–234 ms，**LPE 核 ~577 ms（慢 2.6 倍）**。
  任何 ≥14 线程的测量都可能被调度到 LPE 核，因此报告中的关键配置都显式绑核。
- **[environment.md](notes/environment.md)** 记录了完整的 Windows 工具链搭建过程，以及让
  handout 的 ISPC 任务系统在 MinGW 下可用的 3 处改动（`GetSystemInfo`、匿名信号量、
  `-DISPC_USE_PTHREADS`），Linux 行为保持不变。
- **prog6**：官方数据集只在 Stanford 机器上。按 handout 的合成数据规格写了
  [gen_synthetic_data.cpp](assignments/asst1/prog6_kmeans/gen_synthetic_data.cpp)，生成的
  `data.dat` 可被原 `readData()` 直接读取，并注明绝对时间不可与官方数据直接比较。

## 5. 当前进度

| Program | 状态 | 说明 |
|---|---|---|
| prog1 mandelbrot 线程 | **完成** | 交错行划分；8 线程 7.61x / 7.20x |
| prog2 fake SIMD intrinsics | **进行中** | 任务分析与实现计划见 [TASK.md](assignments/asst1/prog2_vecintrin/TASK.md) |
| prog3 ISPC mandelbrot | 环境验证 | starter 状态：单核 3.12x，`--tasks` 6.39x |
| prog4 ISPC sqrt | 环境验证 | starter 状态：3.52x / 33.49x |
| prog5 ISPC saxpy | 环境验证 | starter 状态：39.7 → 75.2 GB/s，内存带宽受限 |
| prog6 kmeans | 环境验证 | starter 状态；合成数据单线程约 112 s |

> prog3–prog6 的数字仅用于确认环境可用，不代表最终提交结果。prog2 的代码与报告由我独立完成，
> 本仓库只公开任务记录。

## 6. 关于作业代码

Stanford CS149 的讲义、作业描述、handout 源码和解答均受课程版权与学术诚信规则约束。
本仓库**不包含**这些内容，只发布：

- 我自己的课程笔记与总结；
- 我自己的测量结果、图表和分析；
- 我自己写的辅助工具与数据生成程序。

prog1 的最终实现也不在仓库中——报告里的数据、CSV 和图表已足以复现分析结论。

## 7. 联系 / 组队

如果你也在做并行计算、性能优化或高性能计算相关的课程项目/比赛，欢迎交流。

- GitHub：`（待填写）`
- 邮箱：`（待填写）`

我比较看重这样的合作方式：各自能独立承担一块实现与测量，愿意把实验数据和结论写清楚，
遇到性能不符合预期时先从测量里找原因。
