#!/bin/bash

APP_NAME="QwenChat"
EXECUTABLE_NAME="$APP_NAME"
PYTHON_ENTRY="app.py"

echo "Cleaning previous builds..."
rm -rf build dist ${APP_NAME}.app __pycache__

echo "Running PyInstaller..."
pyinstaller --noconfirm --windowed --onefile --name "$EXECUTABLE_NAME" "$PYTHON_ENTRY"
if [ $? -ne 0 ]; then
  echo "PyInstaller failed. Exiting."
  exit 1
fi

echo "Creating .app bundle structure..."
mkdir -p ${APP_NAME}.app/Contents/MacOS
mkdir -p ${APP_NAME}.app/Contents/Resources

echo "Moving executable..."
mv dist/$EXECUTABLE_NAME ${APP_NAME}.app/Contents/MacOS/$EXECUTABLE_NAME
chmod +x ${APP_NAME}.app/Contents/MacOS/$EXECUTABLE_NAME

echo "Writing Info.plist..."
cat > ${APP_NAME}.app/Contents/Info.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" 
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
 <dict>
  <key>CFBundleName</key>
  <string>$APP_NAME</string>
  <key>CFBundleDisplayName</key>
  <string>$APP_NAME</string>
  <key>CFBundleExecutable</key>
  <string>$EXECUTABLE_NAME</string>
  <key>CFBundleIdentifier</key>
  <string>com.yourname.$APP_NAME</string>
  <key>CFBundleVersion</key>
  <string>1.0</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSMinimumSystemVersion</key>
  <string>10.15</string>
  <key>CFBundleIconFile</key>
  <string>app</string>
 </dict>
</plist>
EOF

echo "Done! Your app bundle is ready: ${APP_NAME}.app"
