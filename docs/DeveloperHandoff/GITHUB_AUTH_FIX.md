# GitHub account chooser loop + missing invite email — what is going on

## Facts (verified on owner machine)

| Item | Value |
|---|---|
| CLI / git credential account | **`addgamestudios-ops`** (User, not an org) |
| Token type | `gho_…` with scopes **`gist`, `repo`, `workflow`** (missing `read:org`) |
| Email invite to `sanyarud@gmail.com` | **Never sent** — collaborator API only accepts a **username** |
| What was invited | GitHub user **`sanyarud`** (guessed from email local-part) with **write** |
| Invite status | Still **pending** until that username accepts |
| Public email search for `sanyarud@gmail.com` | **0 results** — we cannot prove that Gmail owns `sanyarud` |
| Standalone handoff repo | Made **public** so clone works without accepting an invite |

---

## Why no email arrived at sanyarud@gmail.com

1. **We did not invite the email address.** GitHub’s “add collaborator” API is `PUT .../collaborators/{username}`. There is no working email-invite path for a **user-owned** private repo from this CLI token.
2. GitHub emails (if any) go to the **notification email on the invited GitHub account** (`sanyarud`), which may be a different address than `sanyarud@gmail.com`, or notifications may be off.
3. Checking Gmail for “invite” therefore shows nothing — that is expected with the above.

**If the developer’s real GitHub login is not `sanyarud`, the invite is sitting on the wrong account.** Paste their real username and we re-invite.

---

## Why the account chooser keeps looping

Common causes on this setup:

1. **Multiple GitHub accounts in the browser** (personal + `addgamestudios-ops` + Google SSO). Picking the wrong one → no invite / no repo → prompt again.
2. **Cursor “Connect GitHub” / OAuth** vs **browser session** are different accounts. Cursor keeps asking until the app is authorized for the account that owns the repo (`addgamestudios-ops`).
3. **Token missing `read:org`** — can worsen org/SSO prompts (this owner is a User account, but OAuth apps still show account pickers).
4. Developer opens invite URL while logged into **Account A**, but invite targets **`sanyarud`** → 404 / empty notifications → looks like a loop.

This is **not** “GitHub doesn’t recognize sanyarud@gmail.com as an invite.” Email was never the invite target.

---

## Exact fix steps

### A) Owner (`addgamestudios-ops`) — stop the chooser loop

1. Browser: open https://github.com/logout and log out **all** sessions.  
2. Also visit https://github.com/logout → confirm. Clear site data for `github.com` if the picker still loops.  
3. Log in **only** as **`addgamestudios-ops`** (the account that owns the repos).  
4. Open https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff and confirm you see Settings.  
5. Cursor: Settings → GitHub / Connect → disconnect, then reconnect **as `addgamestudios-ops`**. Do not pick a personal account.  
6. Optional CLI refresh on the owner PC:

```powershell
gh auth logout --hostname github.com
gh auth login --hostname github.com --web --git-protocol https
# pick addgamestudios-ops; include repo (+ read:org if offered)
gh auth status
gh api user --jq .login   # must print addgamestudios-ops
```

### B) Developer — get the code **now** (no invite needed)

Handoff repo is **public**:

```powershell
git clone https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git
cd RedMMOTitan-DeveloperHandoff
# read Docs/DeveloperHandoff/START_HERE_UK.md
start TitanFundamentals.uproject
```

### C) Developer — accept write access (for push / private Titan)

1. Log into GitHub as the account that should own the work (confirm username at https://github.com/settings/profile).  
2. If that username **is** `sanyarud`, open:  
   - https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff/invitations  
   - https://github.com/addgamestudios-ops/RedMMOTitan/invitations  
3. Or: https://github.com/notifications → filter Invites.  
4. If username is **not** `sanyarud`, send the owner that username; do not wait for Gmail.

### D) Owner — invite the correct person by username

```powershell
gh api -X PUT repos/addgamestudios-ops/RedMMOTitan-DeveloperHandoff/collaborators/CORRECT_USERNAME -f permission=push
gh api -X PUT repos/addgamestudios-ops/RedMMOTitan/collaborators/CORRECT_USERNAME -f permission=push
```

Or UI: repo → Settings → Collaborators → Add people → **username** (email only works in the UI when GitHub can resolve it; API path used here required username).

---

## What you must paste if access is still wrong

**The developer’s GitHub username** (e.g. from https://github.com/settings/profile), not only `sanyarud@gmail.com`.  
We already invited `sanyarud`; if that is wrong, say so and we invite the right login.
