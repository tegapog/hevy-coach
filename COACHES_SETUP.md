# Coaches + Telegram food — setup

You already have the Hevy→Supabase sync running. This adds:
- **Telegram food logger** — text/voice-note what you ate; it logs macros to Supabase and replies. (Workouts still come from Hevy.)
- **Training coach** — nightly Telegram message: what to put on the bar. Works off your Hevy data.
- **Nutrition coach** — nightly Telegram message: macros vs bodyweight trend + one change.

## What you need to create (signups)
| Thing | Where | Gives you | Needed for |
|---|---|---|---|
| Telegram bot | `t.me/botfather` → `/newbot` | **bot token** | everything below |
| Your chat id | message the bot once, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and read `chat.id` | **chat id** | coaches messaging you |
| Gemini key | aistudio.google.com → API key | **key** (free tier) | parsing food text |
| Groq key | console.groq.com → API keys | **key** (free tier) | voice notes (skip if you only type) |
| USDA key | `fdc.nal.usda.gov/api-key-signup` | **key** (free) | food macros |

> Telegram gotcha: a bot **cannot message you first**. You must open the chat and press **Start** once — then the coaches can reach you forever.

## Add these GitHub secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather token |
| `TELEGRAM_CHAT_ID` | your chat id |
| `GEMINI_API_KEY` | Gemini key |
| `GROQ_API_KEY` | Groq key (optional — omit if text-only) |
| `USDA_API_KEY` | USDA key |
| `GEMINI_MODEL` | *(optional)* e.g. `gemini-2.5-flash` if the default is unavailable |

(`DATABASE_URL` and `HEVY_API_KEY` are already set.)

## Turn it on
- The workflows are already in the repo:
  - **Telegram food logger** runs every 5 min.
  - **Coaches (nightly)** runs ~21:05 London.
- Test now: Actions → **Telegram food logger → Run workflow**, then text your bot `2 eggs and 30g whey`. You should get "Got it — logging now" then a macro summary. Check Supabase `food_log`.
- Test the coach: Actions → **Coaches (nightly) → Run workflow** → you get two Telegram messages.

## Notes
- The training coach uses a **28-day** window (the guide's default). While you rebuild consistency it may say "not enough sessions" — add repo variable/secret `COACH_WINDOW_DAYS=84` to widen it, or just keep training and it fills in.
- You don't log RPE in Hevy, so rising lifts get "repeat exactly". **Log RPE on your top sets in Hevy** and the coach will start auto-adding load.
- Food logger handles **food, supplements, bodyweight**. Mention a lift and it reminds you Hevy already has it.
