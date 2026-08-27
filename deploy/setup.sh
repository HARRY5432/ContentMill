#!/bin/bash
set -e

sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv ffmpeg git cron

cd /opt
if [ ! -d "contentfarming" ]; then
    git clone https://github.com/YOUR_USERNAME/contentfarming.git || cp -r ~/contentfarming /opt/contentfarming
fi
cd /opt/contentfarming

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "EDIT /opt/contentfarming/.env WITH YOUR SECRETS"
fi

sudo cp contentfarming.service /etc/systemd/system/
sudo cp contentfarming.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable contentfarming.timer
sudo systemctl start contentfarming.timer

echo ""
echo "=== SETUP COMPLETE ==="
echo "1. Edit /opt/contentfarming/.env with your API keys"
echo "2. Place client_secrets.json and token.json in /opt/contentfarming/"
echo "3. Check status: systemctl status contentfarming.timer"
echo "4. View logs: journalctl -u contentfarming.service -f"
echo "5. Manual run: systemctl start contentfarming.service"

</content>