#!/usr/bin/bash
set -euo pipefail
task_src=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
task_build=${1:-"$task_src/build-nord"}
if [[ -f $task_build/build.ninja ]]; then
    # Reconfigure even with identical options to refresh the embedded Git revision.
    meson setup --reconfigure --buildtype=release -Dcompton=false -Dwith_docs=false -Dunittest=true "$task_build" "$task_src"
else
    meson setup --buildtype=release -Dcompton=false -Dwith_docs=false -Dunittest=true "$task_build" "$task_src"
fi
ninja -C "$task_build" -j8
meson test -C "$task_build" --print-errorlogs
printf 'Built %s/src/picom\n' "$task_build"
