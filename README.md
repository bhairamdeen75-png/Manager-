# Manager — Telegram Group Management Bot

Made with ❤️ TEAMVB

Advanced group management bot — anti-spam (flood control), raid protection,
smart link/scam detection, banned-word filters, new-member captcha + rules gate,
notes, auto-responses, XP/leaderboard, polls/quiz, reminders, pomodoro, and full
mute/ban/kick/warn moderation. 100% free — no paid APIs used anywhere.

## Features

**Moderation & safety**
- 🔐 Captcha verification for new members (math captcha, auto-kick on timeout)
- 📜 Rules-accept gate — members stay muted until they tap "I Accept"
- 🚫 Anti-spam / flood control — fast repeat messages auto-mute the sender
- 🚨 **Raid protection** — 5+ joins in a short window auto-locks the group
  (configurable via `/setraidlimits`), then applies a temporary soft slow-mode
  after unlock (Bot API has no native slow-mode setter, so this is enforced
  at the application level: extra-fast messages are deleted).
- 🔗 **Smart link/scam detection** — catches normal URLs *and* obfuscated ones
  (`t . me`, `t(dot)me`, `bit[dot]ly`, spaced-out domains, common scam phrases),
  not just keyword matching.
- 🧹 Word filters, media-type restriction, /lock & /unlock
- ⚠️ Warn system (auto-ban after N warnings) and full manual moderation
  (/mute /unmute /ban /unban /kick /warn /unwarn /warnings /info)
- 🗒️ Admin log channel — moderation actions get logged to a channel you set

**Group vibe**
- 🌙 Night mode — auto-mutes the group on a daily schedule
- 📌 Auto-pin admin messages
- 🧹 Auto-delete join/leave service messages
- 📢 /tagall — mentions members the bot has seen chatting

**Utility & fun**
- 📝 Notes manager — `/save`, trigger replies via `#hashtag`
- 🤖 Custom auto-responses to any trigger phrase
- ⭐ XP system + `/leaderboard`
- 📊 Native Telegram polls & quizzes
- ⏰ `/remindme`, 🍅 `/pomodoro`
- 📖 `/define` — free dictionary lookups (dictionaryapi.dev, no key needed)
- 📈 `/stats` — group activity overview
- 🩺 `/health` HTTP endpoint for uptime monitoring

Run `/help` inside any group for the full command list.

## Local setup

```bash
git clone <your-repo-url>
cd telegram-group-bot
pip install -r requirements.txt
export BOT_TOKEN="your-bot-token-from-botfather"
export MONGO_URI="mongodb://localhost:27017"     # ya Atlas connection string
python bot.py
```

**MongoDB chahiye** — do free options:
- Local: `mongod` install karke localhost pe chalao (`MONGO_URI=mongodb://localhost:27017`).
- Hosted (recommended, free forever tier): [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) pe free M0 cluster banao, connection string lo (`mongodb+srv://user:pass@cluster.../`), usko `MONGO_URI` me daalo.

## Step-by-step: GitHub + Render + UptimeRobot (bot 24x7 chalane ke liye)

### 1. Bot banao BotFather se
1. Telegram me `@BotFather` ko message karo → `/newbot`
2. Name aur username do → tumhe ek **BOT_TOKEN** milega, usko safe rakho.
3. Bot ko apne group me add karo aur **admin** banao (Delete messages, Ban users, Restrict members ki permissions do).
4. BotFather me `/setprivacy` → apne bot ko choose karo → **Disable** karo, taaki bot group ke normal messages bhi dekh sake (filters/anti-spam ke liye zaroori).

### 2. Code GitHub pe daalo
```bash
cd telegram-group-bot
git init
git add .
git commit -m "Initial commit: group management bot"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

### 3. Render pe deploy karo
1. [render.com](https://render.com) pe account banao aur GitHub connect karo.
2. **New +** → **Web Service** → apna GitHub repo select karo.
3. Settings:
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
   - **Instance Type**: Free is fine — data ab MongoDB me store hota hai, isliye Render ka ephemeral filesystem data ko affect nahi karta.
4. **Environment Variables** me add karo:
   - `BOT_TOKEN` = tumhara BotFather token
   - `OWNER_IDS` = tumhari Telegram user id (optional)
   - `MONGO_URI` = tumhara MongoDB Atlas (ya kisi bhi hosted Mongo) connection string
   - `MONGO_DB_NAME` = database ka naam (optional, default `telegram_manager_bot`)
5. Deploy karo. Render tumhe ek URL dega jaise `https://telegram-group-bot-xxxx.onrender.com` — ye Flask keep-alive server hai, `bot.py` khud polling se Telegram se connect ho jayega.

### 4. UptimeRobot se bot ko sleep hone se bachao
Render ka free web service ~15 min inactivity ke baad sleep ho jata hai. Isse rokne ke liye:
1. [uptimerobot.com](https://uptimerobot.com) pe free account banao.
2. **Add New Monitor** → Monitor Type: **HTTP(s)**.
3. URL: `https://<tumhara-render-url>/ping`
4. Monitoring Interval: **5 minutes**.
5. Save karo — ab UptimeRobot har 5 minute me tumhare Render app ko ping karega aur wo sleep nahi hoga.

(Alternative: cron-job.org bhi same tarike se use kar sakte ho.)

## Commands (group me)

**Moderation** (kisi user ke message pe reply karke use karo):
- `/mute [minutes]` — mute karo (bina minutes ke = hamesha)
- `/unmute` — unmute
- `/ban` / `/unban <user_id>` — ban/unban
- `/kick` — group se nikalo (dobara join kar sakta hai)
- `/warn` / `/unwarn` / `/warnings` — warning system

**Filters:**
- `/addfilter <word>` — banned word add karo
- `/removefilter <word>` — hatao
- `/filters` — list dekho

**Welcome:**
- `/setwelcome <text>` — captcha solve hone ke baad ka message

Sab moderation/filter commands sirf **group admins** hi use kar sakte hain.

## Config (env vars, sab optional except BOT_TOKEN aur MONGO_URI)
| Variable | Default | Matlab |
|---|---|---|
| `BOT_TOKEN` | — | BotFather se mila token (required) |
| `MONGO_URI` | `mongodb://localhost:27017` | MongoDB connection string (required for real deployment) |
| `MONGO_DB_NAME` | `telegram_manager_bot` | Database ka naam |
| `OWNER_IDS` | — | Comma-separated owner user IDs |
| `FLOOD_MSG_LIMIT` | 5 | Kitne messages |
| `FLOOD_TIME_WINDOW` | 7 | Kitne seconds me |
| `FLOOD_MUTE_MINUTES` | 10 | Flood pe mute duration |
| `MAX_WARNS` | 3 | Kitni warnings ke baad ban |
| `CAPTCHA_TIMEOUT_SECONDS` | 90 | Captcha solve karne ka time |

## Note on data persistence
Bot **MongoDB** use karta hai saara data (warns, filters, notes, XP, settings,
stats) store karne ke liye — SQLite nahi. Isliye Render ke free tier ka
ephemeral filesystem koi issue nahi hai: data Mongo me (locally ya Atlas pe)
rehta hai, redeploy/restart se safe hai. Bas `MONGO_URI` sahi se set hona
chahiye. MongoDB Atlas ka free M0 cluster (512MB) is bot ke liye kaafi hai.
