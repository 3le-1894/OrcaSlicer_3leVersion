#!/bin/bash
set -euo pipefail
maintenance=$(cd -- "$(dirname "$0")/.." && pwd)
case_dir=$(mktemp -d)
trap 'rm -rf -- "$case_dir"' EXIT
# Extract only the reviewed functions; never source/execute the updater entry point.
python3 -B - "$maintenance/orca-custom-update" "$case_dir" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text();d=Path(sys.argv[2])
(d/'directory-function').write_text(s[s.index('run_directory_build() {'):s.index('prepare_companion() {')])
(d/'companion-function').write_text(s[s.index('prepare_companion() {'):s.index('require_idle() {')])
(d/'validate-function').write_text(s[s.index('validate_run() {'):s.index('run_directory_build() {')])
PY
for scenario in success failure missing toolmissing; do
 mkdir "$case_dir/$scenario"
 cat > "$case_dir/$scenario/case.sh" <<'CASE'
set -euo pipefail
source_dir=$1;scenario=$2;functions=$3;jobs=1;sandbox=()
source "$functions/directory-function"
bash() {
 [[ "$*" != *' -i '* ]] || return 99
 if [[ "$scenario" == success || "$scenario" == failure ]]; then mkdir -p "$source_dir/build/package"; fi
 if [[ "$scenario" == failure ]]; then return 42; fi
 if [[ "$scenario" == toolmissing ]]; then return 127; fi
}
run_directory_build
CASE
 if /bin/bash "$case_dir/$scenario/case.sh" "$case_dir/$scenario" "$scenario" "$case_dir"; then
  [[ "$scenario" == success ]] || { echo 'FAIL false packaging success'; exit 1; }
 else [[ "$scenario" != success ]] || exit 1; fi
done
# A failed final guard after readiness confirmation must precede any service stop.
cat > "$case_dir/wait.sh" <<'CASE'
set -euo pipefail
case_root=$1
source "$case_root/companion-function"
require_orca_closed(){ :; }
require_idle(){ :; }
systemctl(){ if [[ "$*" == *'--property=ActiveState'* ]]; then echo active; else touch "$case_root/SERVICE_MUTATED"; fi; }
read(){ answer=yes; }
validate_run(){ return 31; }
prepare_companion
CASE
if /bin/bash "$case_dir/wait.sh" "$case_dir"; then echo 'FAIL drift guard ignored'; exit 1; fi
[[ ! -e "$case_dir/SERVICE_MUTATED" ]]
# Rollback's validation hook does not touch source or run-contract tools.
/bin/bash -eu -c 'source "$1/validate-function"; mode=rollback; validate_run' _ "$case_dir"
echo 'PASS directory-only shell packaging success/failure/missing-output; post-wait guard blocks service stop; rollback bypasses build identity'
