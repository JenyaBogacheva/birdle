# Deployment Guide — Birdle AI

**Goal:** Deploy backend + frontend to free hosting with minimal config.

**Time estimate:** 30-45 minutes

---

## Prerequisites

- [ ] GitHub account
- [ ] Project pushed to GitHub repo
- [ ] API keys ready:
  - `OPENAI_API_KEY`
  - `EBIRD_TOKEN`

---

## Part 1: Backend Deployment (Render)

**Why Render:** Free tier, built-in Poetry support, simple setup.

### Steps

1. **Sign up:** [render.com](https://render.com) → Connect GitHub

2. **Create Web Service:**
   - Click "New +" → "Web Service"
   - Select your `birds` repository
   - Configure:
     - **Name:** `bird-id-api` (or your choice)
     - **Region:** Oregon (or closest to you)
     - **Branch:** `main`
     - **Root Directory:** Leave empty (uses repo root)
     - **Runtime:** `Python 3`
     - **Build Command:** `cd services/backend && poetry install --no-dev`
     - **Start Command:** `cd services/backend && poetry run uvicorn app.main:app --host 0.0.0.0 --port $PORT`
     - **Instance Type:** `Free`

3. **Environment Variables:**
   - Click "Environment" tab
   - Add:
     - `OPENAI_API_KEY` = your-key
     - `EBIRD_TOKEN` = your-token
     - `FRONTEND_BASE_URL` = `*` (will update after frontend deployed)
     - `PYTHON_VERSION` = `3.11.0`

4. **Deploy:**
   - Click "Create Web Service"
   - Wait 5-10 minutes for build
   - Note your backend URL: `https://bird-id-api.onrender.com`

5. **Test:**
   ```bash
   curl https://your-backend-url.onrender.com/health
   ```
   Should return: `{"status": "ok"}`

---

## Part 2: Frontend Deployment (Vercel)

**Why Vercel:** Instant React/Vite deployment, free tier, auto HTTPS.

### Steps

1. **Sign up:** [vercel.com](https://vercel.com) → Connect GitHub

2. **Import Project:**
   - Click "Add New..." → "Project"
   - Select your `birds` repository
   - Configure:
     - **Framework Preset:** Vite
     - **Root Directory:** `frontend`
     - **Build Command:** `npm run build` (Vercel auto-detects)
     - **Output Directory:** `dist` (auto-detected)

3. **Environment Variables:**
   - Add before deploying:
     - `VITE_API_BASE_URL` = `https://your-backend-url.onrender.com`
       (use the URL from Part 1, Step 4)

4. **Deploy:**
   - Click "Deploy"
   - Wait 2-3 minutes
   - Note your frontend URL: `https://bird-id-something.vercel.app`

5. **Update Backend CORS:**
   - Go back to Render dashboard
   - Update `FRONTEND_BASE_URL` to your Vercel URL
   - Backend will auto-redeploy (2-3 minutes)

6. **Test:**
   - Open your Vercel URL in browser
   - Submit: "small red bird with crest in New York"
   - Should identify Northern Cardinal

---

## Part 3: Verification Checklist

**Backend:**
- [ ] `/health` returns 200 OK
- [ ] Logs show no errors in Render dashboard
- [ ] Environment variables set correctly

**Frontend:**
- [ ] Site loads without errors
- [ ] Can submit observation form
- [ ] Results appear with species info
- [ ] Images load from Macaulay Library
- [ ] No CORS errors in browser console

**End-to-End:**
- [ ] Test case 1: "red bird with crest in Texas" → Northern Cardinal
- [ ] Test case 2: "small brown bird in California" → Multiple species
- [ ] Test case 3: "colorful parrot in Sydney, Australia" → Australian parrots
- [ ] Loading states work smoothly
- [ ] Error states display helpful messages

---

## Troubleshooting

### Backend build fails
- Check Poetry version: Render should auto-detect from `pyproject.toml`
- Verify `PYTHON_VERSION=3.11.0` in environment variables
- Check build logs for specific error

### Backend starts but crashes
- Check Render logs: Dashboard → Logs tab
- Verify API keys are set and valid
- Ensure start command includes `--host 0.0.0.0 --port $PORT`

### Frontend builds but API calls fail
- Check CORS error in browser console
- Verify `VITE_API_BASE_URL` is set correctly (no trailing slash)
- Verify `FRONTEND_BASE_URL` on backend matches Vercel URL
- Check Network tab for actual API URL being called

### "Network Error" or timeouts
- Render free tier sleeps after 15 min inactivity
- First request after sleep takes 30-60 seconds to wake up
- This is normal for free tier

---

## Alternative: Railway (Backend)

If Render doesn't work, try Railway:

1. **Sign up:** [railway.app](https://railway.app)
2. **New Project** → Deploy from GitHub
3. **Configure:**
   - Select `services/backend` as root
   - Railway auto-detects Poetry
   - Set environment variables same as Render
   - Start command: `poetry run uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. **Generate Domain** in Railway settings
5. Follow same testing steps

---

## Cost Estimates

**Free tier limits:**
- **Render:** 750 hours/month (good for demos)
- **Vercel:** 100 GB bandwidth, unlimited requests
- **OpenAI:** Pay-per-use (~$0.50-2.00 for demo session)
- **eBird:** Free API, rate limited

**Total monthly:** $0-5 for showcase period

---

## Next Steps After Deployment

1. **Test thoroughly** with demo cases
2. **Create DEMO.md** with example queries (see below)
3. **Update README** with live demo link
4. **Share** with live link first

---

## Post-Deployment: Files to Create

### 1. DEMO.md (root of repo)

```markdown
# Live Demo

🔗 **Try it here:** https://your-app.vercel.app

## Test Cases

Try these examples to see different system behaviors:

### 1. Clear Identification (High Confidence)
**Input:** "I saw a small red bird with a crest in New York"
**Expected:** Northern Cardinal with high confidence, image, details

### 2. Multiple Species (Medium Confidence)
**Input:** "Medium brown bird with spotted breast in California"
**Expected:** Multiple thrush species, ranked by likelihood

### 3. Global Coverage
**Input:** "Colorful parrot in Sydney, Australia"
**Expected:** Australian parrot species (Rainbow Lorikeet, etc.)

### 4. Clarification Request (Low Confidence)
**Input:** "Small bird" (Location: Texas)
**Expected:** System asks for more details (color, size, behavior)

### 5. Marine Bird
**Input:** "Large white bird diving for fish in Florida"
**Expected:** Pelican or similar seabird species
```

### 2. README.md Enhancement

Add this section at the top of existing README:

```markdown
## 🚀 Live Demo

**Try it now:** https://your-app.vercel.app

Test with: *"small red bird with a crest in New York"*

## Architecture

- **Frontend:** React + Vite + Tailwind (deployed on Vercel)
- **Backend:** FastAPI + MCP (deployed on Render)
- **AI:** OpenAI GPT-4o-mini for identification reasoning
- **Data:** eBird API v2 for regional bird observations
- **Images:** Macaulay Library (Cornell Lab)

## Quality Metrics

- ✅ 44 passing tests (unit + integration)
- ✅ Full type checking (mypy)
- ✅ Structured logging with latency tracking
- ✅ Graceful error handling and retries
- ✅ Content moderation
- ✅ Global coverage (all continents)
```

---

## Timeline

1. **Backend deployment:** 15 minutes
2. **Frontend deployment:** 10 minutes
3. **Testing & verification:** 10 minutes
4. **Documentation:** 15 minutes

**Total:** ~45-60 minutes to go live

---

## Support

If you encounter issues:
1. Check service logs (Render/Vercel dashboards)
2. Verify environment variables
3. Test backend `/health` endpoint independently
4. Check browser console for frontend errors

Most issues are environment variables or CORS configuration.
