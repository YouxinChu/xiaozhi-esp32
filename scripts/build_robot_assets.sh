#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ASSET_ROOT="$ROOT/components/espressif2022__esp_emote_assets"
WORK="${TMPDIR:-/tmp}/orika-robot-assets"
rm -rf "$WORK"
GIF_DIR="$WORK/gifs"
mkdir -p "$GIF_DIR" "$WORK/robot_eyes" "$WORK/320_240"

# The official Asset Generator uses GIF files for Box-3B. Keep this pipeline
# GIF-based; do not convert to EAF, which is a different runtime format.
python3 "$ROOT/scripts/make_emotion_gifs.py" >/dev/null
# Preserve the official icons and fallback animations. Only the four official
# names above are replaced by the robot-eye GIFs.
cp "$ASSET_ROOT/emoji_large"/*.gif "$WORK/robot_eyes/" 2>/dev/null || true
cp "$ASSET_ROOT/emoji_large"/*.bin "$WORK/robot_eyes/" 2>/dev/null || true
cp /tmp/orika-emotion-gifs/A_idle.gif "$WORK/robot_eyes/neutral.gif"
cp /tmp/orika-emotion-gifs/A_listening.gif "$WORK/robot_eyes/listen.gif"
cp /tmp/orika-emotion-gifs/A_thinking.gif "$WORK/robot_eyes/confused.gif"
cp /tmp/orika-emotion-gifs/A_speaking.gif "$WORK/robot_eyes/Happy.gif"
cp "$ASSET_ROOT/320_240/layout.json" "$WORK/320_240/layout.json"
cp "$ASSET_ROOT/320_240/config.json" "$WORK/320_240/config.json"
python3 - "$WORK/320_240/emote.json" <<'PY'
import json, sys
target = sys.argv[1]
items = [
  {'emote':'neutral','src':'neutral.gif','loop':True,'fps':20},
  {'emote':'listen','src':'listen.gif','loop':True,'fps':20},
  {'emote':'confused','src':'confused.gif','loop':True,'fps':20},
  {'emote':'Happy','src':'Happy.gif','loop':True,'fps':20},
  # Compatibility aliases for older Oraki ROMs; all point to GIF assets.
  {'emote':'orika_a_idle','src':'neutral.gif','loop':True,'fps':20},
  {'emote':'orika_a_listening','src':'listen.gif','loop':True,'fps':20},
  {'emote':'orika_a_thinking','src':'confused.gif','loop':True,'fps':20},
  {'emote':'orika_a_executing','src':'confused.gif','loop':True,'fps':20},
  {'emote':'orika_a_speaking','src':'Happy.gif','loop':True,'fps':20},
]
json.dump(items, open(target, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
PY
python3 "$ASSET_ROOT/scripts/spiffs_assets/build.py" \
  --text_font "$ASSET_ROOT/font/font_puhui_common_20_4.bin" \
  --resolution "$WORK/320_240" \
  --res_path "$WORK/robot_eyes" \
  --wakenet_model "$ASSET_ROOT/wakenet/srmodels.bin"
cp "$ASSET_ROOT/scripts/spiffs_assets/build/face/output/assets.bin" "$ROOT/../box3-web-flasher/public/assets/box3b-robot-eyes-assets.bin"
echo "Generated $ROOT/../box3-web-flasher/public/assets/box3b-robot-eyes-assets.bin"
