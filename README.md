# Obsidian Agent

A scheduled automation framework for [Obsidian](https://obsidian.md) vaults. Runs jobs on a cron schedule to deliver notifications and research digests based on your vault content — without ever modifying your notes.

## What it does

**Task notifications** — Every morning, get an email listing tasks with upcoming or overdue due dates, pulled directly from your vault. No manual review required.

**Research digests** — Weekly, get a markdown report on configured topics (e.g. "agentic coding", "personal knowledge management") deposited into your vault's inbox. Claude searches the web and optionally consults your existing notes to surface what's genuinely new.

More job types are planned.

## How it works

Obsidian Agent reads your vault, indexes it into a local database, and runs jobs against that index. All automation outputs are either:
- **Emails** sent to you directly
- **New notes** placed in a designated `BotInbox/` folder inside your vault

Your existing notes are never modified, moved, or deleted. The system is additive-only.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- An Obsidian vault
- A Gmail or Fastmail account (for email delivery)
- A [Claude](https://claude.ai) subscription (for research digest jobs)

## Setup

**1. Install**

```bash
git clone https://github.com/yourusername/obsidian-agent
cd obsidian-agent
uv sync
```

**2. Configure**

```bash
cp config/config.yaml.example ~/.config/obsidian-agent/config.yaml
```

Edit the config file to set your vault path, email settings, and job preferences.

**3. Set your email password**

Add to `~/.bashrc` (or equivalent):

```bash
export OBSIDIAN_AGENT_SMTP_PASSWORD="your-app-password"
```

For Gmail: enable 2FA, then generate an app password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).

**4. Build the index**

```bash
obsidian-agent index
obsidian-agent status   # verify it looks right
```

**5. Run a job manually**

```bash
obsidian-agent run task_notification
```

**6. Schedule with cron**

```cron
0 7 * * *   obsidian-agent index && obsidian-agent run task_notification
0 18 * * 0  obsidian-agent index && obsidian-agent run research_digest && obsidian-agent promote
```

## Safety

Obsidian Agent is designed to be safe to run against a vault you care about:

- Jobs have no write access to your vault
- The only component that writes into the vault is the `promote` command, and it only creates new files under `BotInbox/`
- No existing note is ever modified or deleted

## Status

This project is under active development. Task notifications are working. Research digest and MCP server support are in progress.
