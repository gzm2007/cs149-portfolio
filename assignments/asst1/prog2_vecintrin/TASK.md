# prog2_vecintrin 任务记录

> 创建：2026-11-01  
> 当前状态：**starter**（两个 TODO 均未实现）  
> 分工：代码、宽度扫描、报告由本人完成；Claude 只提供思路、骨架提示和 review，不代写实现。
> 说明：本公开副本只保留任务记录，不含 handout 源码与解答；文中指向 `main.cpp`、`CS149intrin.h` 等的链接仅用于标注原始作业文件。

## 1. 任务来源与目标

- 课程：Stanford CS149 Fall 2023
- 作业：Assignment 1, Program 2 — *Vectorizing Code Using SIMD Intrinsics*（20 分）
- 要求：用 `CS149intrin.h` 里的 **fake vector intrinsics**，把 `clampedExpSerial` 向量化。
- 作业说明：[../README.md](../README.md#L111)（Program 2 部分，第 111–145 行）

`clampedExpSerial` 的语义（[main.cpp:222](main.cpp#L222)）：

```c
for each i:
  x = values[i];
  y = exponents[i];
  if y == 0:
    output[i] = 1
  else:
    result = x;
    count = y - 1;
    while count > 0:
      result *= x;
      count--;
    if result > 9.999999f:
      result = 9.999999f;
    output[i] = result;
```

## 2. 必做：`clampedExpVector`

位置：[main.cpp:243](main.cpp#L243)

**硬性要求**

- 对**任意** `N` 和 `VECTOR_WIDTH` 成立，不要求 `VECTOR_WIDTH` 整除 `N`，也允许 `N < VECTOR_WIDTH`。
- 不能读写 `values` / `exponents` / `output` 的越界位置。
- 正确实现 `y == 0` 和 clamp 到 `9.999999f` 两个分支。

**关键概念**

- **predicated execution**：每个 `_cs149_v*` 都接受 mask；mask 为 0 的 lane 不会被写。
- **尾部处理**：最后一组只覆盖剩余元素，可用 `_cs149_init_ones(min(VECTOR_WIDTH, N - i))`。
- **发散循环**：各 lane 的指数不同，循环次数不同。整条向量继续执行，但只对仍需乘的 lane 生效；
  用 `_cs149_vgt_int` 维护活跃 lane，用 `_cs149_cntbits` 判断是否还有 lane 需要继续。
- **`y == 0`**：让 `result` 初始化为 `1`，然后只乘 `count` 次；`count == 0` 的 lane 自然保持 1。
- **clamp**：比较 `result > 9.999999f` 生成 mask，只在 mask 命中的 lane 写入上限值。

**容易踩的坑**

- `absVector`（[main.cpp:180](main.cpp#L180)）在 `N % VECTOR_WIDTH != 0` 时会越界——范例本身不是完整的尾部安全实现。先想清楚它为什么有问题，再写自己的循环。
- 寄存器运算不会越界；只有 `vload` / `vstore` 会访问内存。store 必须用只覆盖本组有效元素的 mask。
- 未初始化的 mask 可能读到垃圾值，必要时显式初始化（如 `_cs149_init_ones(0)`）。

## 3. 加分题：`arraySumVector`

位置：[main.cpp:268](main.cpp#L268)

- 可假设 `VECTOR_WIDTH` 是 2 的幂，且 `N % VECTOR_WIDTH == 0`。
- 串行是 `O(N)`；目标为 `N / VECTOR_WIDTH + log2(VECTOR_WIDTH)`（退而求其次是 `+ VECTOR_WIDTH`）。
- 思路：先按向量累加，再用 `_cs149_hadd_float`（相邻两两相加）和 `_cs149_interleave_float`
  （偶数下标移到前半）交替做 `log2(VECTOR_WIDTH)` 次归约，最后取 lane 0。

## 4. 可用指令速查

| 类别 | 指令 |
|---|---|
| 掩码 | `_cs149_init_ones(first)`、`_cs149_mask_not`、`_cs149_mask_and`、`_cs149_mask_or`、`_cs149_cntbits` |
| 搬运 | `_cs149_vload_float/int`、`_cs149_vstore_float/int`、`_cs149_vset_float/int`、`_cs149_vmove_float/int` |
| 算术 | `_cs149_vadd/vsub/vmult/vdiv/vabs_float/int` |
| 比较 | `_cs149_vgt/vlt/veq_float/int` |
| 归约 | `_cs149_hadd_float`、`_cs149_interleave_float` |
| 调试 | `addUserLog()`、`CS149Logger.printLog()` |

完整定义见 [CS149intrin.h](CS149intrin.h)，模拟实现见 [CS149intrin.cpp](CS149intrin.cpp)（重点看 `vgt`、`hadd`、`interleave`）。

## 5. 实施步骤

- [ ] 通读 `CS149intrin.h`，理解 mask 与 predicated execution 的语义。
- [ ] 阅读 `absVector` 范例，弄清它在尾部为什么会越界。
- [ ] 实现 `clampedExpVector`，先保证小规模正确，再考虑指令数。
- [ ] 运行 `-s 16`、`-s 3`、`-s 10000`，三个规模都应为 `Passed!!!`。
- [ ] 用 `-l` 查看逐条指令的 lane 占用，确认 mask 行为符合预期。
- [ ] 实现 `arraySumVector`，验证 bonus 的 `ARRAY SUM` 为 `Passed!!!`。
- [ ] 扫描 `VECTOR_WIDTH = 2 / 4 / 8 / 16`，每次运行 `-s 10000` 并记录统计数据。
- [ ] **把 `VECTOR_WIDTH` 恢复为 4**，重新编译确认。
- [ ] 写 `results/report.md`：扫描表 + 利用率趋势解释。
- [ ] 请 Claude review 实现与报告。

## 6. 构建与验证

在 `prog2_vecintrin/` 目录下：

```bash
make
./myexp.exe -s 16       # 默认规模，必做 + bonus 都应通过
./myexp.exe -s 3        # 尾部 / 非整除 / N < VECTOR_WIDTH
./myexp.exe -s 10000    # 作业要求的性能统计规模
./myexp.exe -l          # 额外打印逐条向量指令日志
```

每次修改 `CS149intrin.h` 后需要重新 `make`。若要彻底重来，可 `make clean`。

**预期输出**

- `CLAMPED EXPONENT (required)` 下为 `Passed!!!`
- `ARRAY SUM (bonus)` 下为 `Passed!!!`（仅当 `N % VECTOR_WIDTH == 0`）
- `printStats()` 输出 `Total Vector Instructions` 与 `Vector Utilization`

## 7. 向量宽度扫描记录

修改 [CS149intrin.h:2](CS149intrin.h#L2) 的 `#define VECTOR_WIDTH`，每次重新编译并运行 `./myexp.exe -s 10000`。

| VECTOR_WIDTH | Total Vector Instructions | Vector Utilization | 备注 |
|---:|---:|---:|---|
| 2 |  |  |  |
| 4 |  |  |  |
| 8 |  |  |  |
| 16 |  |  |  |

`rand()` 未设种子，输入数据可复现；`values` / `exponents` 的前 `N` 个元素在不同宽度下相同，因此统计量可直接比较。

扫完后务必把 `VECTOR_WIDTH` 改回 `4`。

## 8. 报告要点（`results/report.md`）

- 说明实现思路：掩码、尾部处理、发散循环、clamp。
- 给出 2/4/8/16 的扫描表。
- 回答作业的问题：宽度增大时 vector utilization 如何变化？为什么？
  - 提示：宽度越大，各 lane 的指数差异越容易让部分 lane 提前完成，`while` 循环中空转的 lane 比例上升。
- 说明性能指标是 **Total Vector Instructions**，不是墙钟时间。
- 如完成 bonus，说明 `arraySumVector` 的复杂度与归约过程。

## 9. 历史参考基线（仅供对照）

以下是 2026-11-01 为验证本机环境，用一份**临时实现**在 `VECTOR_WIDTH = 4` 下测得的数据，临时实现已删除，starter 已恢复：

| 测试 | Total Vector Instructions | Vector Utilization |
|---|---:|---:|
| `-s 16` | 143 | 75.2% |
| `-s 3` | 39 | 59.6% |
| `-s 10000` | 94,495 | 72.0% |

这些数字只用于判断自己的实现是否大致合理，**不是标准答案**；你的实现不同，指令数和利用率就可能不同。

## 10. 交付物

- [ ] [main.cpp](main.cpp)：`clampedExpVector` + `arraySumVector` 实现
- [ ] `results/report.md`：扫描数据与趋势解释
- [ ] `CS149intrin.h` 的 `VECTOR_WIDTH` 已恢复为 4
- [ ] 工作区无多余构建产物（`*.o`、`myexp.exe` 可按需清理）

## 11. 相关文件

- [main.cpp](main.cpp) — 需要修改的文件
- [CS149intrin.h](CS149intrin.h) — 指令声明与向量宽度
- [CS149intrin.cpp](CS149intrin.cpp) — 指令的模拟实现
- [logger.h](logger.h) / [logger.cpp](logger.cpp) — 统计与日志
- [../README.md](../README.md#L111) — Program 2 作业原文
- 本地引导计划（个人工作区，未随仓库发布）

## 12. 会话记录

- **2026-11-01**：确认本机环境可编译、可运行；用临时实现验证了必做与 bonus，随后恢复 starter。
- **2026-11-01**：配置本地开发工具的通知（细节不随仓库发布）。
- **2026-11-01**：创建本任务记录，开始由本人独立实现。
