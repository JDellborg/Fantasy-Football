# ⚽ FPL Weekly Roundup for Teams

This posts a banter-filled weekly update for our Fantasy Premier League leagues
into a Microsoft Teams chat. It runs by itself, for free, on GitHub. Once it's
set up, you don't need to touch it.

**Leagues covered** (set in `config.json`):
- Classic: 462321
- Main H2H: 462400
- Champions H2H: 939684

**What's in each update:** Manager of the Week, Wooden Spoon, the classic table
with movers, a form guide (last 4 gameweeks) and streaks, captain hits and
flops, best and worst transfers, points hits, chips played, bench regret,
differentials, results and upsets for both H2H leagues, and season records.

**When it posts:** GitHub checks every morning at 08:00 UTC. As soon as a
gameweek is completely finished (bonus points confirmed), it posts once.

---

## One-time setup (about 10 minutes)

### Step 1: Create the Teams Workflow (this gets you a secret web link)
1. In Teams, open your FPL group chat.
2. Click the **…** (more options) at the top of the chat and choose **Workflows**.
3. Search for **"Send webhook alerts to a chat"** (it may be called
   *"Post to a chat when a webhook request is received"*) and select it.
4. Give it a name such as `FPL Weekly`, then click **Next**.
5. Check that the chat selected is your FPL chat, then click **Add workflow**.
6. Teams shows you a long web link. **Copy it** and keep it private: anyone
   with this link can post into your chat.

### Step 2: Give the link to GitHub as a secret
1. Open this repository on GitHub: <https://github.com/jdellborg/fantasy-football>
2. Click **Settings**, then in the left menu **Secrets and variables** and then **Actions**.
3. Click **New repository secret**.
4. Name: `TEAMS_WEBHOOK_URL`. Secret: paste the link from Step 1. Click **Add secret**.

### Step 3: Preview it (nothing gets posted)
1. In the repository, click the **Actions** tab. If GitHub asks, click to enable workflows.
   (If it says "No workflows found", go to **Settings → Actions → General**, choose
   **Allow all actions and reusable workflows**, click **Save**, and ask Claude to re-push.)
2. Click **FPL weekly update** on the left, then **Run workflow**.
3. Leave **mode** on `preview` and click the green **Run workflow** button.
4. Wait about 1 minute, then click the run. Scroll down to see the full update
   as it would appear. (The *fpl-update* download at the bottom contains the
   raw files.)

### Step 4: Send the first one
Run the workflow again, this time choosing **mode = `post`**. It should appear in
your Teams chat within seconds. After that, it posts automatically every gameweek.

---

## Customising

- **Nicknames:** in `config.json`, map a manager's FPL team ID to a nickname, e.g.
  `"nicknames": { "1234567": "The Gaffer" }`. You can find a manager's team ID
  in the web address when you click their team on the FPL site.
- **Banter lines:** edit `fpl_weekly/banter.py`. Each section has a list of
  lines, so add as many as you like. Words in `{curly brackets}` get filled in
  automatically.
- **Re-send an older gameweek:** run the workflow manually and type a gameweek number.

## Troubleshooting

- **Nothing posted this week:** the gameweek may not be finished yet (the FPL
  site confirms points the morning after the last match). Check the Actions
  tab for a red ❌ and open it to see why.
- **The Teams link stopped working:** recreate the workflow (Step 1) and update
  the secret (Step 2).
- GitHub pauses scheduled jobs in repositories with no activity for 60 days.
  Each weekly post records the gameweek it sent, which counts as activity, so
  this shouldn't happen during the season.

## For the technically curious
Python 3, standard library only, using the public FPL API. Run the tests with
`python -m unittest discover tests` (they use made-up data). Run it locally with
`python -m fpl_weekly` to preview, or add `--post` with `TEAMS_WEBHOOK_URL` set.
