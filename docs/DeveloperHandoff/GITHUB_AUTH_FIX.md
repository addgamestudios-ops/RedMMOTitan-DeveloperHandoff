# GitHub multi-account chooser — browser fix

## Facts

| Item | Value |
|---|---|
| Repo owner account | **`addgamestudios-ops`** |
| Standalone handoff | https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff (**public** — clone without invite) |
| Full Titan repo | https://github.com/addgamestudios-ops/RedMMOTitan (**private**) |

---

## Why the account chooser keeps looping

1. **Multiple GitHub accounts in the browser** (personal + studio + Google SSO). Picking the wrong one → no access → prompt again.
2. Developer opens a private-repo URL while logged into an account that is not a collaborator → 404 / empty notifications → looks like a loop.
3. Cached sessions for `github.com` keep reopening the account picker.

This is a browser / session issue, not a problem with the handoff content itself.

---

## Exact fix steps (browser only)

### A) Owner (`addgamestudios-ops`) — stop the chooser loop

1. Open https://github.com/logout and log out **all** sessions.  
2. Clear site data for `github.com` if the picker still loops.  
3. Log in **only** as **`addgamestudios-ops`**.  
4. Open https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff and confirm you see the repo.  
5. Optional CLI refresh on the owner PC:

```powershell
gh auth logout --hostname github.com
gh auth login --hostname github.com --web --git-protocol https
# pick addgamestudios-ops; include repo scope
gh auth status
gh api user --jq .login   # must print addgamestudios-ops
```

### B) Developer — get the code now (no invite needed)

Handoff repo is **public**:

```powershell
git clone https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git
cd RedMMOTitan-DeveloperHandoff
# read Docs/DeveloperHandoff/START_HERE_UK.md or START_HERE.md
start TitanFundamentals.uproject
```

### C) Developer — private Titan write access

1. Log into GitHub as the account that should own the work (confirm username at https://github.com/settings/profile).  
2. Accept any pending collaborator invite for `RedMMOTitan`, or ask the owner to invite that **username**.  
3. Or: https://github.com/notifications → filter Invites.

---

## What to send the owner if private access is still wrong

**The developer’s GitHub username** (from https://github.com/settings/profile), not only an email address.
