#!/bin/bash
# Syncs main KDM extension files to SafariExtensionFiles and to your Safari Xcode project.
# First time: run with your Resources path to save it. After that, just run ./sync_safari_extension.sh

KDM_DIR="$(cd "$(dirname "$0")" && pwd)"
PATH_FILE="$KDM_DIR/.safari_extension_path"
FILES="content.js background.js manifest.json watchfilmy-capture.js"

# Always update SafariExtensionFiles
for f in $FILES; do
  if [ -f "$KDM_DIR/$f" ]; then
    cp "$KDM_DIR/$f" "$KDM_DIR/SafariExtensionFiles/$f"
    echo "Updated SafariExtensionFiles/$f"
  fi
done

# If path given as argument, use it and save for next time
if [ -n "$1" ]; then
  if [ -d "$1" ]; then
    echo "$1" > "$PATH_FILE"
    echo "Saved path for next time: $1"
  else
    echo "Warning: '$1' is not a directory."
    echo "Example: ./sync_safari_extension.sh \"/Users/hussnainasif/Downloads/kdm/Shared (Extension)/Resources\""
    exit 1
  fi
fi

# Copy to saved path if we have one
SAFARI_RESOURCES=""
if [ -f "$PATH_FILE" ]; then
  SAFARI_RESOURCES=$(cat "$PATH_FILE")
fi
if [ -n "$SAFARI_RESOURCES" ] && [ -d "$SAFARI_RESOURCES" ]; then
  for f in $FILES; do
    if [ -f "$KDM_DIR/$f" ]; then
      cp "$KDM_DIR/$f" "$SAFARI_RESOURCES/$f"
      echo "Updated Safari Xcode project: $SAFARI_RESOURCES/$f"
    fi
  done
  echo "Done. Open Xcode and press Cmd+B to rebuild, then Cmd+R to run."
else
  if [ ! -f "$PATH_FILE" ] || [ ! -d "$SAFARI_RESOURCES" ]; then
    echo ""
    echo "Safari Xcode path not set. First time, run:"
    echo "  ./sync_safari_extension.sh \"/Users/hussnainasif/Downloads/kdm/Shared (Extension)/Resources\""
    echo "(Use the real path to your kdm project's 'Shared (Extension)/Resources' folder.)"
    echo "After that, just run ./sync_safari_extension.sh and code will auto-update there."
  fi
fi
