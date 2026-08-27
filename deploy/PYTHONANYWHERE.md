# PythonAnywhere Deployment Guide

## 1. Sign Up
- Go to https://www.pythonanywhere.com → Create free account
- Choose "Beginner" (free tier)

## 2. Upload Files
- Go to **Files** tab → Upload all project files to `/home/yourusername/contentfarming/`
- Or use git: open **Bash console** and run:
```bash
cd /home/yourusername
git clone https://github.com/YOUR_USERNAME/contentfarming.git
```

## 3. Install Dependencies
Open a **Bash console**:
```bash
cd /home/yourusername/contentfarming
pip install --user yt-dlp google-api-python-client google-auth-oauthlib google-auth-httplib2
```

## 4. Configure Secrets
In **Files** tab, create `.env` in project folder with your keys:
```
OPENROUTER_API_KEY=sk-or-v1-YOUR_KEY
OPENROUTER_MODEL=openrouter/fusion
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
TELEGRAM_CHAT_ID=YOUR_CHAT_ID
```

## 5. Upload Auth Files
Upload `client_secrets.json` and `token.json` to project folder via **Files** tab.

## 6. Schedule Daily Task
- Go to **Tasks** tab → **Scheduled tasks**
- Add new task:
  - Time: `06:00`
  - Command: `cd /home/yourusername/contentfarming && python pipeline.py`
- Click **Create**

## Notes
- Free tier: 1 scheduled task, limited CPU time per day
- Check task logs in **Tasks** tab after each run
- ffmpeg is pre-installed on PythonAnywhere

</content>