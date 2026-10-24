#!/bin/bash
# Mac mini'de botu otomatik başlatmak için launchd servisi kurar.
# Kullanım: bash setup_autostart.sh

PLIST="$HOME/Library/LaunchAgents/com.firatdere.gcplanner.plist"
BOT_DIR="$HOME/Telegrem-GC-Planner"
PYTHON="$BOT_DIR/venv/bin/python3"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.firatdere.gcplanner</string>

    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$BOT_DIR/bot.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$BOT_DIR</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>TELEGRAM_BOT_TOKEN</key>
        <string>$(grep TELEGRAM_BOT_TOKEN "$BOT_DIR/.env" | cut -d '=' -f2)</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$BOT_DIR/bot.log</string>

    <key>StandardErrorPath</key>
    <string>$BOT_DIR/bot.log</string>
</dict>
</plist>
EOF

# Servisi yükle ve başlat
launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST"

echo "✅ Servis kuruldu. Bot şimdi çalışıyor ve yeniden başlatmalarda otomatik başlayacak."
echo "📄 Log: tail -f $BOT_DIR/bot.log"
echo "🛑 Durdurmak: launchctl unload $PLIST"
