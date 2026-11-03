// runon.cpp -- a tiny `taskset` for Windows, with hybrid-core (P/E) awareness.
//
// Not part of the CS149 handout; this is a local measurement helper.
//
// Why: on a hybrid CPU (e.g. Core Ultra 9 285H: 6 P-cores + 8 E-cores + 2 LPE
// cores) the Windows scheduler can migrate a compute thread between cores of
// very different speed. For the CS149 scaling experiments you want to pin the
// process to a known set of cores so that the numbers mean something.
//
// Build (MSYS2 UCRT64):
//     g++ -O2 -municode -static -o runon.exe runon.cpp
// -municode is required for wmain(); -static keeps the exe independent of the
// MinGW runtime DLLs, so it also runs when ucrt64\bin is not on PATH.
//
// Usage:
//     runon --list                          show logical CPU -> core -> efficiency class
//     runon --p    <exe> [args...]          pin to the highest-efficiency (P) cores
//     runon --e    <exe> [args...]          pin to the lower-efficiency (E/LPE) cores
//     runon --all  <exe> [args...]          no affinity restriction (sanity check)
//     runon --mask 0x3F <exe> [args...]     pin to an explicit affinity mask
//
// Exit code is the child's exit code.

#include <windows.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

struct CoreInfo {
    int coreIndex = 0;
    int efficiencyClass = 0;  // larger == less efficient on hybrid CPUs
    std::vector<int> cpus;    // logical processor ids in this physical core
};

static std::vector<CoreInfo> enumerateCores() {
    std::vector<CoreInfo> cores;
    DWORD len = 0;
    GetLogicalProcessorInformationEx(RelationProcessorCore, nullptr, &len);
    if (len == 0) return cores;

    std::vector<char> buf(len);
    if (!GetLogicalProcessorInformationEx(RelationProcessorCore,
                                          reinterpret_cast<PSYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX>(buf.data()),
                                          &len)) {
        return cores;
    }

    int coreIndex = 0;
    for (DWORD off = 0; off < len;) {
        auto *info = reinterpret_cast<PSYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX>(buf.data() + off);
        if (info->Relationship == RelationProcessorCore) {
            CoreInfo ci;
            ci.coreIndex = coreIndex++;
            ci.efficiencyClass = static_cast<int>(info->Processor.EfficiencyClass);
            // One logical processor per bit set in the group mask.
            ULONG_PTR m = info->Processor.GroupMask[0].Mask;
            for (int b = 0; b < 64; ++b) {
                if (m & (static_cast<ULONG_PTR>(1) << b)) ci.cpus.push_back(b);
            }
            cores.push_back(ci);
        }
        off += info->Size;
    }
    return cores;
}

static void printList(const std::vector<CoreInfo> &cores) {
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    printf("logical processors: %lu\n", static_cast<unsigned long>(si.dwNumberOfProcessors));
    printf("physical cores    : %zu\n\n", cores.size());
    printf("%-6s %-10s %-8s %s\n", "core", "effclass", "cpus", "type");
    int minEff = 1 << 30, maxEff = -1;
    for (const auto &c : cores) {
        if (c.efficiencyClass < minEff) minEff = c.efficiencyClass;
        if (c.efficiencyClass > maxEff) maxEff = c.efficiencyClass;
    }
    for (const auto &c : cores) {
        char cpus[256] = {0};
        size_t used = 0;
        for (size_t i = 0; i < c.cpus.size(); ++i) {
            used += static_cast<size_t>(snprintf(cpus + used, sizeof(cpus) - used, i ? ",%d" : "%d", c.cpus[i]));
            if (used >= sizeof(cpus) - 8) break;
        }
        const char *type;
        if (minEff == maxEff) type = "uniform";
        else if (c.efficiencyClass == maxEff) type = "fast (P)";
        else if (c.efficiencyClass == minEff) type = "slow (E/LPE)";
        else type = "middle";
        printf("%-6d %-10d %-8s %s\n", c.coreIndex, c.efficiencyClass, cpus, type);
    }
    if (minEff != maxEff) {
        printf("\nnote: on this machine the HIGHER effclass is the faster group (measured with\n"
               "      mandelbrot serial: effclass-max CPUs ~216-223 ms, effclass-min CPUs\n"
               "      ~229-234 ms, and CPUs 14/15 (low-power E) ~577 ms). Always re-verify on a\n"
               "      new machine with `runon --mask` timings before trusting the labels.\n");
    }
}

static ULONG_PTR maskForEfficiency(const std::vector<CoreInfo> &cores, bool wantFast) {
    int minEff = 1 << 30, maxEff = -1;
    for (const auto &c : cores) {
        if (c.efficiencyClass < minEff) minEff = c.efficiencyClass;
        if (c.efficiencyClass > maxEff) maxEff = c.efficiencyClass;
    }
    ULONG_PTR mask = 0;
    for (const auto &c : cores) {
        bool isFast;
        if (minEff == maxEff) {
            isFast = true;  // uniform CPU: every core counts as "fast"
        } else {
            isFast = (c.efficiencyClass == maxEff);
        }
        if (isFast != wantFast) continue;
        for (int cpu : c.cpus) {
            if (cpu < 64) mask |= (static_cast<ULONG_PTR>(1) << cpu);
        }
    }
    return mask;
}

// Resolve the executable the way a shell would: exact path, path + ".exe", then PATH search.
static std::wstring resolveExe(const std::wstring &exe) {
    if (GetFileAttributesW(exe.c_str()) != INVALID_FILE_ATTRIBUTES) return exe;

    std::wstring withExt = exe;
    if (withExt.size() < 4 || _wcsicmp(withExt.c_str() + withExt.size() - 4, L".exe") != 0) {
        withExt += L".exe";
        if (GetFileAttributesW(withExt.c_str()) != INVALID_FILE_ATTRIBUTES) return withExt;
    }

    wchar_t found[MAX_PATH];
    DWORD n = SearchPathW(nullptr, withExt.c_str(), nullptr, MAX_PATH, found, nullptr);
    if (n > 0) return std::wstring(found, n);

    return withExt;
}

static std::wstring joinCommandLine(int argc, wchar_t **argv, int start) {
    std::wstring cmd;
    for (int i = start; i < argc; ++i) {
        if (i > start) cmd += L' ';
        std::wstring a = argv[i];
        bool needQuote = a.find_first_of(L" \t") != std::wstring::npos;
        if (needQuote) cmd += L'"';
        cmd += a;
        if (needQuote) cmd += L'"';
    }
    return cmd;
}

static void usage() {
    printf(
        "runon -- a tiny taskset for Windows (hybrid-aware)\n\n"
        "  runon --list                        list logical CPU / core / efficiency class\n"
        "  runon --p    <exe> [args...]        pin to P cores (highest efficiency)\n"
        "  runon --e    <exe> [args...]        pin to E/LPE cores\n"
        "  runon --all  <exe> [args...]        run without affinity restriction\n"
        "  runon --mask 0x3F <exe> [args...]   pin to an explicit affinity mask\n");
}

int wmain(int argc, wchar_t **argv) {
    auto cores = enumerateCores();

    if (argc < 2) {
        usage();
        return 2;
    }

    std::wstring mode = argv[1];
    if (mode == L"--list" || mode == L"-l") {
        printList(cores);
        return 0;
    }
    if (mode == L"--help" || mode == L"-h" || mode == L"-?") {
        usage();
        return 0;
    }

    ULONG_PTR mask = 0;
    bool restrict = true;
    int childArgStart = 0;

    if (mode == L"--p") {
        mask = maskForEfficiency(cores, true);
        childArgStart = 2;
    } else if (mode == L"--e") {
        mask = maskForEfficiency(cores, false);
        childArgStart = 2;
    } else if (mode == L"--all") {
        restrict = false;
        childArgStart = 2;
    } else if (mode == L"--mask") {
        if (argc < 4) {
            usage();
            return 2;
        }
        mask = static_cast<ULONG_PTR>(_wcstoui64(argv[2], nullptr, 0));
        childArgStart = 3;
    } else {
        usage();
        return 2;
    }

    if (childArgStart >= argc) {
        usage();
        return 2;
    }

    std::wstring exe = resolveExe(argv[childArgStart]);
    std::wstring cmd = joinCommandLine(argc, argv, childArgStart);

    STARTUPINFOW si;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    PROCESS_INFORMATION pi;
    ZeroMemory(&pi, sizeof(pi));

    // CREATE_SUSPENDED so the affinity is in place before the child runs anything.
    if (!CreateProcessW(exe.c_str(), cmd.data(), nullptr, nullptr, TRUE, CREATE_SUSPENDED, nullptr, nullptr, &si, &pi)) {
        fwprintf(stderr, L"runon: CreateProcessW failed for %ls (error %lu)\n", exe.c_str(), GetLastError());
        return 127;
    }

    if (restrict) {
        if (!SetProcessAffinityMask(pi.hProcess, mask)) {
            fwprintf(stderr, L"runon: SetProcessAffinityMask(0x%llX) failed (error %lu)\n",
                     static_cast<unsigned long long>(mask), GetLastError());
            TerminateProcess(pi.hProcess, 126);
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
            return 126;
        }
        if (const char *verbose = getenv("RUNON_VERBOSE")) {
            (void)verbose;
            printf("runon: affinity mask = 0x%llX\n", static_cast<unsigned long long>(mask));
        }
    }

    ResumeThread(pi.hThread);
    WaitForSingleObject(pi.hProcess, INFINITE);

    DWORD rc = 0;
    GetExitCodeProcess(pi.hProcess, &rc);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return static_cast<int>(rc);
}
