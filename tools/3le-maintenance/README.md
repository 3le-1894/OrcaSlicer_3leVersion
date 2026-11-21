# 3le maintenance integration candidate

Prepared 2026-11-18. Uncommitted source preparation only. Installed runtime, updater and desktop entry are unchanged. Do not install or invoke build/deploy from this candidate until independent review, commit approval and a separately approved owner-run build/activation phase.

## Source policy

The dedicated branch is `maintenance/calculator-startup-integration` in `/home/elemental/Applications/OrcaCustom/worktrees/calculator-startup-integration`, rooted at 6f05ad94cc4c89caacc3f0e83f8272025670ad2c. Native changes are exactly the reviewed production R3 plus permanent startup correction. The two held checkouts are not migration inputs.

`check_source.py` is read-only. It requires the exact repository root/branch, base ancestry, a clean index/worktree (including untracked files), committed maintenance artifacts, and exact reviewed native/package/fixture hashes from `policy.json`. Consequently this uncommitted candidate MUST fail its real gate. After review and owner-approved commit it can pass; HEAD is not hardcoded forever to the base commit. New upstream merges or adaptations require review, tests and explicit pinned-identity/dependency-policy refresh. Branch and hashes are maintenance consistency controls, not signatures or authorization to deploy arbitrary future commits.

Dependency hashes are retained from the preserved successful owner-run environment. The explicit prefix is the existing `work/dual-nozzle-reliability/deps/build/OrcaSlicer_dep/usr/local`, used read-only. The first native build in this new worktree must be fresh. Existing build caches are rejected unless source root, compiler, Ninja Multi-Config generator, dependency prefix, Python root and disconnected-fetch policy match. No old native build directory is copied or relocated. No `-d`, `-u` or arbitrary build flags are accepted by the candidate updater. Changing compiler/ABI/dependencies requires a newly reviewed configuration/cache plan.

## Versioned calculator

`orca-print-calculator/baseline` is the original 0.6.2 wheel-derived source. `source` is the exact production 0.6.2+3le.connect.r3 tree, with Python and embedded generated HTML/JS. This is not the missing upstream frontend project; no rewrite is claimed. `plugin.patch`, `PROVENANCE.json` and `reproduce.py` retain the deterministic transformation. `orca_print_calculator_any.whl` is the exact existing production artifact (SHA-256 70209977be3719782beab5a6bc8e0b083fe597f35d84dc7cad42f8a6f2edac1b).

File-only reconstruction, with a NEW output directory, is:

```
python3 -B tools/3le-maintenance/orca-print-calculator/reproduce.py /absolute/new/output
```

It checks pinned inputs, reconstructs the source, builds RECORD and writes the fixed-order/timestamp wheel. It does not install or access user data. The updater validates this package but does not replace installed wheels. Upstream marketplace replacement is separate from native updates and could discard these customizations; no user update settings were changed.

## Candidate updater

`orca-custom-update.original` is the exact installed updater at preparation time. The candidate `orca-custom-update` points explicitly to this worktree; its old deployed copy still points at the held worktree. Merely committing here does not change the desktop shortcut.

For build/deploy, the candidate gates source BEFORE log-directory creation, window closure, compilation or service operations. It fixes the dependency/Python/local-uv paths through `ORCA_EXTRA_BUILD_ARGS`, disables fetching, and uses a network-isolated bubblewrap build with a cleared environment, compiler cache disabled, and host files read-only except this new worktree. Dependencies outside it remain read-only. The default is one compiler job (explicit 1–4 accepted). Unavailable tooling, packaging/network requirements or tracked-source writes fail closed; no download/install fallback or dirty-file whitelist is supplied.

It keeps the existing cloud/height and TravelOptimization tests and adds the maintenance Python contracts, exact calculator reconstruction, and the two actual readiness C++ fixtures with Debug assertions (`-UNDEBUG` plus forced assertion header). Those native fixtures were previously owner-qualified with synthetic GUI boundaries; this new maintenance test wiring has NOT been compiled or executed. Their historical copied README's unexecuted label describes initial fixture preparation. Real wx/backend/platform lifecycle qualification is still separate.

Source/cache checks run again after building and before deployment. `build.json` retains the real committed HEAD and status through the original provenance code. The required maintenance files are committed and policy-checked; the full revision identifies their policy. The original package checks, backup/swap recovery, process closure, companion-job confirmation, stop/start and rollback logic are unchanged. `rollback` remains available independently of the clean source gate; it never rebuilds. No updater pulls/fetches or switches a source branch automatically.

## Checks and remaining owner steps

Run only non-native preparation tests now:

```
python3 -B -m unittest discover -s tools/3le-maintenance/tests -p 'test_*.py'
bash -n tools/3le-maintenance/orca-custom-update
```

Synthetic Git-query adapter tests exercise committed/dirty/untracked/staged/wrong-branch/wrong-root/wrong-ancestry/missing-file states without making commits. File/cache tests reject altered accepted code and incompatible caches. A real read-only gate run must reject this current uncommitted state. Positive real committed-source and native build/packaging behavior remain unexecuted until approved.

Next: independent review of packaging, source policy, updater sandbox/dependency mapping and test wiring; owner-approved commit in this branch only (no held work); then separately approved owner-run build and package verification. If build_linux.sh generates tracked translation/source changes, stop for review rather than weaken the clean gate. This updater requests directory-runtime packaging only, omitting optional AppImage creation. No AppImage download/helper path is requested. A pre-existing build/package is refused: preserve/archive that generated directory explicitly before a later approved run, rather than silently reusing stale outputs. Required launcher/binary/profile outputs and exact executable resources/tools/uv/uv must exist, even in build-only mode. Failed packaging or missing output stops the run. The existing 4-job desktop script remains deployed and unchanged.

Only after those gates should a separate owner activation replace the deployed updater script (retaining its old copy), then the ordinary desktop entry can use this source path. No updater installation command is issued in this source candidate. There is no need to replace the accepted production runtime now. Commit/push, native builds and updater/runtime activation have not occurred.


## R3 review corrections (2026-11-20)

SI-01: directory runtime is the sole artifact contract; no `-i` or AppImage fallback. A fresh output is required and the directory inventory is sealed after tests. The run refuses a pre-existing package directory; do not delete evidence automatically.

SI-02: after acquiring the updater lock, capture the clean committed starting HEAD, policy hash, all maintenance helper/package/fixture identities and external tools. Recheck the same run identity after build/tests. `build.json` is generated from that captured identity, never a fresh HEAD lookup. The sealed package and copied staged inventory are compared, including launcher/binary content and executable permissions. After companion job/results confirmation the final guard runs before stop, and again immediately before runtime swap. Rollback bypasses these source/build checks. Checks occur at boundaries rather than locking ordinary Git editors: keep the source unchanged throughout an owner-run build/deploy.

SI-03: policy pins the exact preserved external uv path/content; it must be a regular executable file before build. Capture verifies the actual supplied build path matches policy. Its bundled resources/tools/uv/uv must also have the approved content and be executable before package sealing/staging/activation. No uv invocation or replacement is part of these checks.

`tests/test_run_contract.py` exercises actual run-contract functions with synthetic files/Git-query responses for clean descendant changes during build and readiness wait, dirty/policy/helper drift, external/bundled uv failure cases and staged package/provenance integrity. `tests/test_packaging.sh` extracts only the relevant shell functions, replaces build/service interactions with stubs, and checks packaging success/failure/missing tooling/missing output, post-wait guard placement, and rollback bypass. It never sources the live updater entry point, invokes a compiler/uv or controls a service. Both are wired into future updater tests. The prior unexecuted native/build caveats still apply.


## R4 narrow review corrections (2026-11-20)

The bundled uv check follows the actual CMake producer, directory packager and runtime lookup: `resources/tools/uv/uv` is the regular executable, while `resources/tools/uv` is its directory. A flat executable at the directory path is not accepted. The pinned external tool/path and run identity rules remain unchanged.

Root `build.json` is reserved: the build-output inventory rejects any existing entry there, including regular files, directories, internal/external/dangling links or a link to the package root. The copied fresh stage is revalidated against the seal before provenance creation. Directory-relative `O_CREAT|O_EXCL|O_NOFOLLOW` creation refuses a pre-existing entry (including one inserted after validation) and never writes through it. Final validation uses explicit stage inventory mode, requires regular non-symlink provenance, reads it without following a symlink and compares it to the captured run identity. A generated provenance file is not allowed back into fresh build-output mode. The updater's provenance operation now receives the seal and stage directory, rather than an unrestricted output filename.

Synthetic regressions cover the actual nested uv layout, flat layout rejection, missing/changed/nonexecutable bundled tool, reserved entries and root-directory symlinks, outside/internal sentinel preservation, a simulated validation/open race, exclusive creation refusal and valid generated-stage provenance. No actual uv, native build or service operation is executed by these tests. SI-01/02 boundary/source/rollback contracts remain unchanged.
