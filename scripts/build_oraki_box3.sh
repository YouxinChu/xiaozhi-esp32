#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$project_dir"

: "${IDF_PATH:?Source ESP-IDF export.sh before running this script}"
rm -f sdkconfig sdkconfig.old
export SDKCONFIG_DEFAULTS="sdkconfig.defaults;sdkconfig.defaults.esp32s3;sdkconfig.oraki-box3.defaults"
wake_words_file="$project_dir/config/wake_words.oraki.json"
idf.py set-target esp32s3
idf.py -DORAKI_WAKE_WORDS_JSON="$wake_words_file" build
idf.py merge-bin

echo "Oraki BOX-3B firmware: $project_dir/build/merged-binary.bin"
echo "Oraki BOX-3B assets:   $project_dir/build/generated_assets.bin"
