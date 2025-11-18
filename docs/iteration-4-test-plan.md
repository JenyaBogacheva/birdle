# Iteration 4 — Manual Test Plan

## Overview

This document provides a repeatable manual test checklist for validating resilience and observability improvements in Iteration 4.

**Test Date:** _[To be filled during testing]_
**Tester:** _[Name]_
**Environment:** Local development (backend: port 8000, frontend: port 5173)

---

## Prerequisites

- [ ] Backend running: `cd /mnt/nfs/users/jenya/birds && poetry run uvicorn services.backend.app.main:app --reload`
- [ ] Frontend running: `cd /mnt/nfs/users/jenya/birds/frontend && npm run dev`
- [ ] Valid API keys in `.env.local`:
  - `OPENAI_API_KEY`
  - `EBIRD_TOKEN`
- [ ] Terminal open to monitor backend logs

---

## Test Cases

### TC-1: Normal Request Flow (Baseline)

**Goal:** Verify normal operation works and logs are structured.

**Steps:**
1. Navigate to `http://localhost:5173`
2. Enter description: "Small red bird with black mask and crest"
3. Enter location: "New York, USA"
4. Click "Identify Bird"
5. Observe loading stages display
6. Wait for results
7. Check backend logs for structured metrics

**Expected Results:**
- ✅ Loading stages appear: "Analyzing..." → "Fetching..." → "Identifying..."
- ✅ Elapsed time counter increments during loading
- ✅ Progress dots animate through stages
- ✅ Results display with Northern Cardinal (or similar)
- ✅ Backend logs show structured JSON with:
  - `operation`, `latency_ms`, `status`, `total_tokens`
  - MCP tool calls with latency tracking
  - Request completion with summary metrics

**Actual Results:**
_[To be filled]_

**Status:** ⬜ Pass / ⬜ Fail

---

### TC-2: MCP Timeout Simulation

**Goal:** Test graceful handling of MCP timeouts.

**Steps:**
1. Edit `services/backend/app/helpers/mcp_client.py`
2. Temporarily change `TOOL_CALL_TIMEOUT = 30.0` to `TOOL_CALL_TIMEOUT = 0.1`
3. Restart backend
4. Submit a normal identification request
5. Observe behavior
6. Restore `TOOL_CALL_TIMEOUT = 30.0`
7. Restart backend

**Expected Results:**
- ✅ Request completes without crashing
- ✅ System returns empty observations fallback (no species data)
- ✅ LLM still attempts identification with limited context
- ✅ Backend logs show warning about MCP timeout with structured metadata
- ✅ Frontend displays results (possibly low confidence or clarification)

**Actual Results:**
_[To be filled]_

**Status:** ⬜ Pass / ⬜ Fail

---

### TC-3: Full Request Timeout

**Goal:** Test overall request timeout handling.

**Steps:**
1. Edit `services/backend/app/routes/identify.py`
2. Temporarily change `IDENTIFY_TIMEOUT = 60.0` to `IDENTIFY_TIMEOUT = 2.0`
3. Restart backend
4. Submit an identification request
5. Wait for timeout
6. Observe frontend error handling
7. Restore `IDENTIFY_TIMEOUT = 60.0`
8. Restart backend

**Expected Results:**
- ✅ Request times out after ~2 seconds
- ✅ Frontend shows timeout error with helpful message
- ✅ Error panel displays "Request Timeout" title
- ✅ Error hint suggests trying again
- ✅ "Try Again" button appears and is functional
- ✅ Backend logs show timeout with 504 status and latency

**Actual Results:**
_[To be filled]_

**Status:** ⬜ Pass / ⬜ Fail

---

### TC-4: Image Fetch Failure (Partial Success)

**Goal:** Test that image failures don't block species identification.

**Steps:**
1. Submit identification request for "Blue Jay in New York"
2. While processing, temporarily disconnect internet or block Macaulay Library
3. Observe results

**Expected Results:**
- ✅ Species identification completes successfully
- ✅ Species shown without image (image_url is null)
- ✅ No photographer credit displayed
- ✅ Backend logs show image fetch warning but continues
- ✅ Overall request succeeds with partial data

**Actual Results:**
_[To be filled]_

**Status:** ⬜ Pass / ⬜ Fail

---

### TC-5: Invalid Location Handling

**Goal:** Test validation of location input.

**Steps:**
1. Enter description: "Red bird"
2. Leave location field empty
3. Click "Identify Bird"
4. Observe validation

**Expected Results:**
- ✅ Frontend form validation prevents submission (browser validation)
- ✅ If bypassed, backend returns 400 error
- ✅ Error message explains location is required
- ✅ Error includes helpful examples

**Actual Results:**
_[To be filled]_

**Status:** ⬜ Pass / ⬜ Fail

---

### TC-6: Network Error Handling

**Goal:** Test frontend resilience to network failures.

**Steps:**
1. Start identification request
2. Stop backend server mid-request
3. Wait for request to fail
4. Observe error handling
5. Restart backend
6. Click "Try Again" button

**Expected Results:**
- ✅ Frontend detects network error
- ✅ Error panel shows "Network Error" with helpful hint
- ✅ "Try Again" button appears
- ✅ Clicking retry resubmits the same observation
- ✅ Second attempt succeeds after backend restart

**Actual Results:**
_[To be filled]_

**Status:** ⬜ Pass / ⬜ Fail

---

### TC-7: Low Confidence / Clarification Display

**Goal:** Test enhanced clarification UI for ambiguous descriptions.

**Steps:**
1. Enter vague description: "A bird"
2. Enter location: "London, UK"
3. Submit request
4. Observe clarification handling

**Expected Results:**
- ✅ System returns clarification question
- ✅ Clarification displayed in prominent yellow box
- ✅ Icon and "Need More Information" heading visible
- ✅ Helpful tip about providing more details shown
- ✅ Box has emphasized styling (border-2, shadow-sm)

**Actual Results:**
_[To be filled]_

**Status:** ⬜ Pass / ⬜ Fail

---

### TC-8: Loading Stage Progression

**Goal:** Test loading stage UI behavior.

**Steps:**
1. Submit a normal request
2. Observe loading stages carefully
3. Note timing of stage transitions
4. Check elapsed time counter

**Expected Results:**
- ✅ Stage 1 ("Analyzing...") appears immediately
- ✅ Stage 2 ("Fetching...") appears after ~2 seconds
- ✅ Stage 3 ("Identifying...") appears after ~5 seconds
- ✅ Progress dots correctly highlight current stage
- ✅ Elapsed time counter increments every second
- ✅ Loading indicator disappears when results arrive

**Actual Results:**
_[To be filled]_

**Status:** ⬜ Pass / ⬜ Fail

---

### TC-9: Log Format Verification

**Goal:** Verify structured logging format and content.

**Steps:**
1. Submit a normal identification request
2. Review backend terminal logs
3. Check for structured log entries

**Expected Results:**
- ✅ Logs contain `extra` fields in structured format
- ✅ Request start log includes: `operation`, `description_length`, `location`
- ✅ MCP tool calls include: `tool`, `operation`, `latency_ms`, `status`
- ✅ OpenAI calls include: `model`, `latency_ms`, `total_tokens`, `status`
- ✅ Request completion includes: `total_latency_ms`, `has_top_species`, `alternate_count`
- ✅ All latencies are in milliseconds (rounded to 2 decimals)
- ✅ Status fields present: "success", "error", "timeout", etc.

**Actual Results:**
_[To be filled]_

**Status:** ⬜ Pass / ⬜ Fail

---

### TC-10: Multiple Retry Attempts

**Goal:** Test retry functionality with multiple failures.

**Steps:**
1. Submit request
2. Stop backend to cause network error
3. Click "Try Again" (should fail again)
4. Start backend
5. Click "Try Again" (should succeed)

**Expected Results:**
- ✅ First retry shows same network error
- ✅ "Try Again" button still available after second failure
- ✅ Third attempt (after backend restart) succeeds
- ✅ Same observation data used in all attempts
- ✅ No data loss between retries

**Actual Results:**
_[To be filled]_

**Status:** ⬜ Pass / ⬜ Fail

---

## Regression Checks

After completing test cases, verify previous iterations still work:

- [ ] **Iteration 1:** Stubbed flow still accessible for testing
- [ ] **Iteration 2:** eBird MCP integration works with valid API keys
- [ ] **Iteration 3:** Images display correctly, alternate species expand/collapse
- [ ] **Global regions:** Test non-US locations (Australia, UK, Japan)

---

## Performance Benchmarks

Record typical latencies for reference:

| Operation | Expected Latency | Actual Latency |
|-----------|------------------|----------------|
| Content moderation | < 500ms | _[Fill]_ |
| Region extraction | < 1000ms | _[Fill]_ |
| eBird observations | < 3000ms | _[Fill]_ |
| OpenAI identification | < 5000ms | _[Fill]_ |
| Species image fetch | < 2000ms | _[Fill]_ |
| **Total request** | **< 15s** | **_[Fill]_** |

---

## Test Summary

**Total Test Cases:** 10
**Passed:** _[Count]_
**Failed:** _[Count]_
**Blocked:** _[Count]_

**Overall Status:** ⬜ Ready for Production / ⬜ Needs Fixes

**Notes:**
_[Additional observations, issues found, or recommendations]_

---

## Sign-off

**Tester:** ________________
**Date:** ________________
**Reviewed By:** ________________
**Date:** ________________
