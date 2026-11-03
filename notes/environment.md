# 本地开发环境（Windows）

> 记录时间：2026-10-25；2026-11-01 整理并更新 prog1 完成状态。
> 目标机器：本地 Windows 11 笔记本（Intel Core Ultra 9 285H）
> 结论：**asst1 六个 program 均已可在本机编译并运行**；其中 prog6 使用本地合成的 `data.dat`（官方数据集只在 Stanford myth 机器上）。目前只有 prog1 完成了作业要求的优化，其余仍是 handout starter 状态。

## 1. 装了什么、装在哪

| 组件 | 版本 | 路径 |
|---|---|---|
| MSYS2 base | 2026-09-27 | `<TOOLCHAIN_ROOT>\msys64` |
| g++ (UCRT64) | 16.2.0 (Rev6) | `<TOOLCHAIN_ROOT>\msys64\ucrt64\bin\g++.exe` |
| GNU Make | 4.4.1 | `<TOOLCHAIN_ROOT>\msys64\usr\bin\make.exe` |
| Intel ISPC | 1.28.1 (LLVM 20.1.8) | `<TOOLCHAIN_ROOT>\ispc-1.28.1\bin\ispc.exe` |
| Python venv | 3.12.10 | `<repo>\.venv`（numpy 2.5.4 / matplotlib 3.11.2 / scikit-learn 1.9.1） |

总占用约 1.75 GB（不含 767 MB 的 `data.dat`）。

### 为什么不是 WSL、不是 MSVC

- 官方要求 myth 机器（Linux），但本机没装 WSL，而且 `wsl --install` 需要重启。
- MSYS2 的 UCRT64 提供 POSIX 风格的 `make`/`mkdir`/`pthread`，Makefile 基本可以原样使用。
- MSVC 路线走不通：ISPC 的 Windows 默认目标链接的是 MSVC 的 Concurrency Runtime（`concrt.h`），而 handout 的 `tasksys.cpp` 又需要 ISPC 任务系统，两者都和 GNU 工具链不兼容（详见第 3 节）。

## 2. 怎么用

### 2.1 打开环境

```powershell
# 方式一：在当前 PowerShell 会话里加 PATH
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass   # 只影响当前窗口，仅首次需要
. .\notes\tools\env.ps1

# 方式二：开一个 cmd 会话（不受 PowerShell 执行策略限制）
.\notes\tools\cmd.cmd

# 方式三：开一个 MSYS2 UCRT64 shell（做 make 构建最顺）
.\notes\tools\msys2-shell.cmd
```

> 本机默认的 Windows PowerShell 5.1 执行策略会拒绝运行未签名的 `.ps1`，所以 `env.ps1` 需要先 `Set-ExecutionPolicy -Scope Process Bypass`；`.cmd` 入口没有这个限制。工具脚本本身是纯 ASCII（避免 PowerShell 5.1 按 ANSI 读取 UTF-8 中文注释导致解析错误）。

### 2.2 各程序的构建与运行

所有命令都在 `assignments/asst1/<program>/` 目录下执行。

| 程序 | 构建 | 运行 |
|---|---|---|
| prog1 mandelbrot 线程 | `make` | `./mandelbrot.exe -t 8 -v 1` |
| prog2 假向量指令 | `make` | `./myexp.exe -s 10000`（`-l` 打印指令日志） |
| prog3 ISPC mandelbrot | `make` | `./mandelbrot_ispc.exe -v 1` / `--tasks` |
| prog4 sqrt | `make` | `./sqrt.exe` |
| prog5 saxpy | `make` | `./saxpy.exe` |
| prog6 kmeans | `make` | `./kmeans.exe`（需 `data.dat`，见第 4 节） |

各目录 `make clean` 可清理产物。

### 2.3 Python 绘图（prog6）

```powershell
.\.venv\Scripts\python.exe assignments\asst1\prog6_kmeans\plot.py
```

生成 `start.png` / `end.png`。注意：`prog6_kmeans/requirements.txt` 里写的是 `matplotlib~=3.6.0`，该版本没有 Python 3.12 的 wheel，**不能用它装**；venv 里装的是不锁版本的 matplotlib 3.11.2（API 兼容，plot.py 实测通过）。

### 2.4 绑核与 P/E 核（Windows 上替代 `taskset`）

Windows 没有 `taskset`，而这块 CPU 是异构的：Windows 调度器可能把计算线程在性能差很多的核之间搬来搬去，直接测出来的线程扩展曲线会失真。为此写了一个小工具 `notes/tools/runon.cpp`（约 250 行，**不属于 handout**）：

```powershell
cd notes\tools
g++ -O2 -municode -static -o runon.exe runon.cpp   # -municode 给 wmain；-static 让 exe 不依赖 MinGW DLL
```

用法（下面的例子假定当前在 `assignments\asst1\<program>\` 目录，所以用 `..\..\..\` 回到仓库根）：

```powershell
..\..\..\notes\tools\runon.exe --list                            # 打印逻辑 CPU / 物理核 / 效率类（与当前目录无关）
..\..\..\notes\tools\runon.exe --p     .\mandelbrot.exe -t 8     # 只绑到高性能核（P 核）
..\..\..\notes\tools\runon.exe --e     .\mandelbrot.exe -t 8     # 只绑到低性能核（E/LPE）
..\..\..\notes\tools\runon.exe --all   .\mandelbrot.exe -t 8     # 不限制（默认行为）
..\..\..\notes\tools\runon.exe --mask 0x3 .\mandelbrot.exe -t 2  # 显式掩码，等价 taskset 0x3
```

实现方式：用 `CreateProcessW(..., CREATE_SUSPENDED)` 起子进程，先 `SetProcessAffinityMask` 再 `ResumeThread`，所以亲和性在子进程执行第一条指令前就已生效（不是启动后再抢着设）。

**本机实测的核拓扑**（`runon --list` + 逐核计时交叉验证）：

| 组 | 逻辑 CPU | 数量 | 单核 mandelbrot 串行耗时 |
|---|---|---|---|
| P 核 | 0, 1, 10, 11, 12, 13 | 6 | ~216–223 ms |
| E 核 | 2–9 | 8 | ~229–234 ms |
| LPE 核（低功耗 E） | 14, 15 | 2 | **~577 ms（慢 2.6 倍）** |

两个坑：

1. **不要相信 `EfficiencyClass` 的直觉**：Windows 在这台机器上给 P 核的是更高的值（1），给 E/LPE 的是 0，和我最初的假设相反。上面那张表是**用计时反推**出来的，换机器请重新验证（`runon --list` 只是一级线索）。
2. **CPU 14/15 是低功耗核，慢 2.6 倍**。任何 ≥14 线程的测量都可能被调度到它们上面，导致曲线尾部塌陷。做 myth 那种 4/8 线程实验时，建议显式绑核，例如：

```powershell
# 只用 4 个 P 核，模拟 myth 的 4 核
..\..\..\notes\tools\runon.exe --mask 0x2403 .\mandelbrot.exe -t 4
# 用全部 6 个 P 核
..\..\..\notes\tools\runon.exe --p .\mandelbrot.exe -t 6
```

实测（prog3 ISPC+tasks，2 个 task 的 starter 代码）：不限制 / 6 个 P 核 / 2 个 P 核 三种绑法下都是 6.1–6.2x，因为 starter 只切了 2 个 task，核数不是瓶颈——这也说明**绑核本身不会改变程序的语义**，只是让测量更可复现。

其它提高测量精度的做法：每个配置跑 3–5 次取最小值（Windows 有后台任务抖动）、插电 + 高性能电源计划、关掉浏览器等吃 CPU 的程序。Windows 上拿不到 Linux `perf` 那样的硬件计数器，prog1 的第 3 小题（每线程计时）只能用 handout 自带的 `CycleTimer.h` 在代码里插桩。

## 3. 对 handout 源码的改动（共 3 处，都是 Windows/MinGW 必需）

`assignments/asst1` 已在单一仓库中扁平化（原独立仓库备份在 `assignments/_git_backup/asst1.git`，不纳入版本控制）；改动可随仓库历史查看。

1. **`prog1_mandelbrot_threads/main.cpp`** — 加 `#include <cstring>`。
   GCC 16 不再隐式包含 `<cstring>`，`memset` 找不到声明。这行在 myth/新 gcc 上同样需要，属于老 handout 与新编译器的正常冲突。

2. **`common/tasksys.cpp`** — MinGW 兼容（3 个 hunk）：
   - `sysconf(_SC_NPROCESSORS_ONLN)` → Windows 下改用 `GetSystemInfo`（新增 `lNumLogicalCores()`）；
   - `sem_open`（POSIX 具名信号量，winpthreads 不支持）→ Windows 下改用静态存储的匿名信号量 `sem_init`；
   - 两者都用 `#ifdef ISPC_IS_WINDOWS` 包住，**Linux 行为不变**。

3. **`prog3/4/5/6` 四个 Makefile** — 追加 `CXXFLAGS+= -DISPC_USE_PTHREADS`。
   `tasksys.cpp` 在 `_WIN32` 下默认选 `ISPC_USE_CONCRT`（MSVC 专属），必须强制走 pthread 分支。该 define 在 Linux 上是 no-op（默认就是 pthreads）。

> 另外提醒：ISPC 在 Windows 目标下会警告 `--pic switches for Windows target will be ignored`，属正常现象，Makefile 里的 `--pic` 无害。链接 ISPC 目标文件时 ld 还可能打印 `Warning: corrupt .drectve at end of def file`，同样是 MinGW 链接 MSVC 风格 COFF 的已知无害警告，程序可以正常运行（prog3/4/5 已实测）。

## 4. prog6 的数据集

官方做法是在 myth 上软链 AFS 的 800MB 数据：

```
ln -s <COURSE_DATA_PATH> ./data.dat
```

本机没有 AFS 访问权限，`data.dat` 也不在 handout 仓库里。因此本地用 handout `main.cpp` 注释里给出的合成数据路径生成了一份同规格数据：

- 文件：`prog6_kmeans/gen_synthetic_data.cpp`（**不是 handout 文件**，是本仓库自己加的辅助程序）
- 规格与官方一致：`M=1e6`、`N=100`、`K=3`、`epsilon=0.1`、`seed=7`；
- 二进制格式完全按 `utils.cpp:writeData()`，`readData()` 可直接读；
- 生成方式：

```powershell
cd assignments\asst1\prog6_kmeans
g++ -O2 -o gen_synthetic_data.exe gen_synthetic_data.cpp utils.cpp
.\gen_synthetic_data.exe          # 写出 ./data.dat（约 767MB）
```

⚠️ 这份数据**不是**官方数据集，所以 prog6 的绝对时间与官方不可比。但 prog6 问的是「相对自身的加速比（≥2.1x）」，瓶颈结构一样（`computeAssignments` 的 O(M·K·N) 距离计算），优化前后的相对加速比仍然成立。写报告时应注明数据来源。

实测：单线程跑完一轮 K-means 约 **112 秒**（`[Total Time]: 112014.793 ms`），是六个程序里最慢的。

## 5. 与 myth 机器的差异（会影响报告结论）

| | myth（官方要求） | 本机 |
|---|---|---|
| CPU | i7-7700K，4 核 8 硬件线程（HT），4.2–4.5 GHz | Ultra 9 285H，6 P 核 + 8 E 核 + 2 LPE 核 = **16 线程，无 HT** |
| SIMD | AVX2（8-wide） | AVX2（8-wide）✅ 一致 |
| 系统 | Linux | Windows 11 |

影响：

- **prog1 的线程扩展曲线**：本机 16 个线程是 16 个物理核，不是 myth 的 8 个 HT 线程。所以「8→16 线程还有没有提升」这一问的答案会完全不同（而且 P/E 核性能差异会让曲线提前拐弯）。
- 建议：每个配置跑 3–5 次取最小值（本机有 E 核调度的抖动），并在报告里写清机器型号与核拓扑。
- **prog3 的「理想 32x」**：4 核 × 8-wide = 32x 是 myth 的上限；本机核数更多，绝对加速比会更高，但**单核 SIMD 加速比（3.1x 左右）**才是这题真正要解释的量，这一点与机器无关。
- 想和 myth 的 4 核可比：用 `notes\tools\runon.exe --mask 0x2403 程序 -t 4` 绑到 4 个 P 核（等价 `taskset 0x2403`），6 个 P 核用 `--p`。绑核工具与实测拓扑见 [2.4 节](#24-绑核与-pe-核windows-上替代-taskset)。

## 6. 网络与下载源（本机实测）

| 地址 | 状态 | 用途 |
|---|---|---|
| 代理 `<PROXY>`（Clash） | ✅ | 全局 HTTP(S) 代理 |
| `github.com` | 修好代理后 ✅ | — |
| `<GITHUB_MIRROR>` + GitHub URL | ✅ | ISPC release 下载（215MB） |
| `<MIRROR_HOST>` | ✅ | MSYS2 发行包、pacman 镜像、pip index |
| `<MSYS2_MIRROR>` | 时通时不通 | 备选源 |
| MSYS2 官方 pacman 仓库 | 无 `ispc` 包 | 必须单独装 ISPC |

pacman 已配置为国内镜像（`/etc/pacman.d/mirrorlist.mingw`、`mirrorlist.msys`，原文件备份为 `.bak`）。

## 7. 从零重建（换机器时）

```powershell
# 1) MSYS2 base（也可用官方镜像）
curl.exe -o msys2-base.tar.xz https://<MIRROR_HOST>/msys2/distrib/x86_64/msys2-base-x86_64-20260927.tar.xz
# 解压到 <TOOLCHAIN_ROOT>\msys64（Windows 自带 tar 支持 xz）

# 2) ISPC（GitHub 直连不通时走镜像）
curl.exe -L -o ispc.zip https://<GITHUB_MIRROR>/https://github.com/ispc/ispc/releases/download/v1.28.1/ispc-v1.28.1-windows.zip

# 3) 初始化并装 gcc/make
<TOOLCHAIN_ROOT>\msys64\msys2_shell.cmd -defterm -no-start -ucrt64 -c "pacman-key --init; pacman-key --populate msys2; pacman -Sy --noconfirm; pacman -S --noconfirm --needed mingw-w64-ucrt-x86_64-gcc make"

# 4) Python 依赖
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install numpy matplotlib scikit-learn -i https://<PYPI_MIRROR>/simple
```

## 8. 已验证的基线数据（本机）

| 程序 | 结果 |
|---|---|
| prog1 | **已完成**（2026-11-01）：交错行划分，串行 view1 ≈ 222 ms / view2 ≈ 127 ms；8 线程 **7.61x / 7.20x**。完整数据见 [`assignments/asst1/prog1_mandelbrot_threads/results/`](../assignments/asst1/prog1_mandelbrot_threads/results/) |
| prog2 | 编译通过；`myexp -s 1000` 报验证失败（`clampedExpVector` 未实现，属 starter 预期） |
| prog3 | ISPC 单核 **3.12x**，ISPC + tasks **6.39x**（未做 handout 的修正，属 starter 状态） |
| prog4 | ISPC **3.52x**，ISPC + tasks **33.49x** |
| prog5 | ISPC 39.7 GB/s → tasks 75.2 GB/s，tasks 加速 **1.90x**（内存带宽受限，符合题目预期） |
| prog6 | 单线程 112 s，`plot.py` 正常出图 |

> 除 prog1 外，其余程序仍是 handout starter 状态，上述数字仅用于确认环境可用。
