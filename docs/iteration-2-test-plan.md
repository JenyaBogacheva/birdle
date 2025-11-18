# Iteration 2 E2E Test Plan

## Prerequisites

### 1. Environment Setup

Create `.env.local` in project root with:

```bash
# Required API Keys
OPENAI_API_KEY=your-actual-openai-api-key
EBIRD_TOKEN=your-actual-ebird-api-token

# Configuration
FRONTEND_BASE_URL=http://localhost:5173
APP_NAME=Birdle AI
DEBUG=true
```

### 2. Server Startup

**Terminal 1 - Backend:**
```bash
cd /mnt/nfs/users/jenya/birds
poetry run uvicorn services.backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd /mnt/nfs/users/jenya/birds/frontend
npm run dev
```

## Test Cases

### Test 1: Clear Distinctive Bird (High Confidence Expected)

**Input:**
- Description: "Small red bird with a prominent crest and black mask around beak"
- Location: "Pennsylvania"
- Observed at: "January 2024"

**Expected Result:**
- ✅ Species identified: Northern Cardinal
- ✅ Confidence: HIGH
- ✅ Reasoning provided explaining distinctive features
- ✅ eBird link working
- ✅ Response time < 5 seconds

**Validation:**
- Check backend logs show:
  - Moderation check passed
  - eBird API call successful
  - OpenAI API call successful with token counts
  - Total latency logged
- Check frontend displays:
  - Green confidence badge
  - Reasoning section visible
  - eBird link functional

### Test 2: Ambiguous Description (Medium Confidence Expected)

**Input:**
- Description: "Small yellow bird with some black markings"
- Location: "New York"

**Expected Result:**
- ✅ Species identified (possibly American Goldfinch)
- ✅ Confidence: MEDIUM
- ✅ Reasoning mentions ambiguity
- ✅ No clarification needed (but reasoning indicates uncertainty)

**Validation:**
- Check yellow confidence badge displayed
- Reasoning mentions need for more details

### Test 3: Vague Description (Low Confidence or Clarification)

**Input:**
- Description: "I saw a bird"

**Expected Result:**
- ⚠️ Either low confidence OR clarification request
- ✅ Clarification section shows helpful follow-up question
- ✅ Question asks about specific features (size, color, behavior)

**Validation:**
- Check clarification box is yellow and visible
- Question is specific and helpful

### Test 4: Regional Species Validation

**Input:**
- Description: "Large blue bird with a crest"
- Location: "Florida"

**Expected Result:**
- ✅ Species: Blue Jay (common in Florida)
- ✅ Regional context used (eBird data shows recent FL observations)
- ✅ Confidence based on regional prevalence

**Validation:**
- Check backend logs show FL region code extracted
- eBird API queried for correct region

### Test 5: Content Moderation

**Input:**
- Description: "inappropriate or offensive content"

**Expected Result:**
- ❌ Request rejected with 400 status
- ✅ Error message displayed in frontend
- ✅ Backend logs warning about moderation failure

### Test 6: Error Handling - No API Keys

**Setup:**
- Remove or invalidate API keys in `.env.local`

**Expected Result:**
- ❌ Appropriate error message
- ✅ Frontend shows error state
- ✅ No crash or hanging

## Success Criteria

All tests should demonstrate:

1. **Functionality:**
   - ✅ OpenAI integration working (structured responses)
   - ✅ eBird MCP integration working (regional data)
   - ✅ Confidence assessment accurate (LLM self-assessment)
   - ✅ Frontend displays all new fields correctly

2. **Performance:**
   - ✅ Response time < 10 seconds for typical requests
   - ✅ Logs show token usage for cost tracking

3. **Reliability:**
   - ✅ Moderation checks before processing
   - ✅ Graceful error handling
   - ✅ No crashes on edge cases

4. **Code Quality:**
   - ✅ All unit tests pass (13/13)
   - ✅ MyPy type checking passes
   - ✅ Frontend build succeeds
   - ✅ No linter errors

## Test Evidence Required

For each test case, capture:
1. Request payload (JSON)
2. Response payload (JSON)
3. Backend log excerpt showing:
   - Moderation result
   - eBird API call
   - OpenAI API call with token counts
   - Total latency
4. Frontend screenshot showing:
   - Confidence badge
   - Reasoning section
   - eBird link
   - Or clarification question if applicable

## Notes

- eBird API has rate limits - space out tests if needed
- OpenAI costs money - use gpt-4o-mini for cost efficiency
- Real API responses will vary - focus on structure and behavior, not exact matches
