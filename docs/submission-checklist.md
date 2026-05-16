# Devpost Submission Checklist — HealthPay Intelligence Agent

**Competition:** Google Cloud Rapid Agent Hackathon — MongoDB Track
**Deadline:** June 12, 2026 (submit by June 11 to be safe)
**Platform:** https://rapid-agent.devpost.com/

---

## Step 1: Pre-flight Checks

### GitHub Repo
- [ ] Repo is **public** (Settings → Danger Zone → Change visibility → Public)
- [ ] `LICENSE` file is visible at repo root (MIT, copyright Leon Huang 2026)
- [ ] `README.md` shows the hackathon section and judging criteria table
- [ ] `.env` is **not** tracked — run `git status` and confirm `.env` is not listed
- [ ] No API keys or secrets in any committed file — run:
  ```bash
  git log --all --full-history -- .env
  grep -r "MONGODB_URI\s*=" --include="*.py" src/ scripts/
  ```
- [ ] Latest code is pushed: `git push origin main`

### Demo Video
- [ ] Video is uploaded to YouTube (unlisted is fine) or Google Drive (public link)
- [ ] Video URL is ready to paste into Devpost

---

## Step 2: Record the Demo Video

**Recommended tools:**
- **macOS:** QuickTime Player → File → New Screen Recording
- **Linux/Windows:** OBS Studio (free, https://obsproject.com)
- **Quick option:** Loom (https://loom.com) — records and hosts automatically

**Steps:**
1. Open terminal, `cd /home/taomi/projects/healthpay-gcp`
2. Start recording (capture terminal window only, not full screen)
3. Follow the script in `docs/demo-video-script.md`
4. Run `python scripts/demo_standalone.py` live
5. Stop recording, export as MP4 at 1080p
6. Upload to YouTube as Unlisted, copy the URL

---

## Step 3: Devpost Registration & Login

1. Go to https://rapid-agent.devpost.com/
2. Click **"Enter"** or **"Register"**
3. Sign up with GitHub (recommended — links your repo automatically) or email
4. Verify email if prompted

---

## Step 4: Fill Out the Submission Form

Navigate to the hackathon page → **"Enter Submission"**

### Required Fields

| Field | Value |
|-------|-------|
| **Project Name** | HealthPay Intelligence Agent |
| **Tagline** | AI-powered healthcare payment reconciliation on MongoDB Atlas + Gemini |
| **Demo Video URL** | [Your YouTube/Loom URL] |
| **GitHub Repository URL** | [Your public GitHub repo URL] |
| **Track** | ✅ Select **MongoDB Track** |

### Description (paste from devpost-writeup.md)
Copy the content of `docs/devpost-writeup.md` into the description field.
Devpost supports Markdown — the formatting will render correctly.

### Built With Tags
Add these tags (Devpost has a tag input field):
```
python  mongodb-atlas  gemini  google-cloud-agent-builder  mcp  fhir  vertex-ai
```

### Team Members
- Add Leon Huang (your Devpost username)
- Solo submission is fine

---

## Step 5: Final Security Check Before Submitting

Run these commands to confirm no secrets are exposed:

```bash
cd /home/taomi/projects/healthpay-gcp

# 1. Confirm .env is not tracked
git ls-files | grep -E "\.env$|\.key$|secret"
# Expected output: nothing (empty)

# 2. Confirm .gitignore covers secrets
cat .gitignore | grep -E "\.env|\.key|secret"
# Expected: lines matching .env, *.key, *secret*

# 3. Scan for hardcoded credentials
grep -rn "mongodb+srv://" --include="*.py" .
grep -rn "AIza" --include="*.py" .
# Expected output: nothing (empty)

# 4. Check .env.example has no real values
cat .env.example
# Should show placeholder values like: MONGODB_URI=mongodb+srv://USER:PASS@cluster.mongodb.net/
```

If any check fails, fix before submitting.

---

## Step 6: Submit

1. Review the preview — confirm video plays, GitHub link works, track is MongoDB
2. Click **"Submit Project"**
3. Screenshot the confirmation page
4. Share the Devpost project URL with the team

---

## Post-Submission

- [ ] Share Devpost URL in team chat
- [ ] Star the project on Devpost (helps visibility)
- [ ] Monitor email for judge questions (respond within 24h)
- [ ] Deadline: June 12, 2026 — no changes after this date

---

*Good luck! The project is solid — 35/35 tests, clean architecture, real problem. 🏆*
