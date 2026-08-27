# Oracle Cloud Deployment Guide

## 1. Create Free VM
- Go to https://cloud.oracle.com → Sign up (free)
- Create VM: Always Free ARM instance (4 OCPUs, 24GB RAM)
- OS: Ubuntu 22.04 or 24.04
- Download SSH key (.pem file)

## 2. Connect
```bash
ssh -i your-key.pem ubuntu@<VM_PUBLIC_IP>
```

## 3. Deploy
```bash
# Upload project files
scp -r -i your-key.pem ./contentfarming ubuntu@<IP>:/home/ubuntu/

# SSH in and run setup
ssh -i your-key.pem ubuntu@<IP>
cd /home/ubuntu/contentfarming
chmod +x deploy/setup.sh
sudo ./deploy/setup.sh
```

## 4. Configure Secrets
```bash
sudo nano /opt/contentfarming/.env
# Paste your API keys from .env.example
```

## 5. Place Auth Files
```bash
scp -i your-key.pem client_secrets.json token.json ubuntu@<IP>:/opt/contentfarming/
```

## 6. Verify
```bash
systemctl status contentfarming.timer    # Check timer is active
journalctl -u contentfarming.service -f  # Watch logs
systemctl start contentfarming.service   # Manual test run
```

## Schedule
Runs daily at 6:00 AM UTC. Edit `/etc/systemd/system/contentfarming.timer` to change time.
