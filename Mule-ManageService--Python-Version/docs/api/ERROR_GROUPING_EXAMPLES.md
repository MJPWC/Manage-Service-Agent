# Error Grouping - Practical Examples

## Example 1: Multiple Errors with Same Correlation ID

### Input Data (5 Errors)
```json
[
  {
    "timestamp": "2026-03-10T10:00:00Z",
    "event_id": "b4d35f24-bd47-4797-a0f8-2135f3b246b8",
    "message": "Failed to create referral",
    "exception": { "Error type": "EXT:CANT_CREATE_REFERRAL" }
  },
  {
    "timestamp": "2026-03-10T10:05:12Z",
    "event_id": "b4d35f24-bd47-4797-a0f8-2135f3b246b8",  ← SAME ID
    "message": "Failed to create referral",
    "exception": { "Error type": "EXT:CANT_CREATE_REFERRAL" }
  },
  {
    "timestamp": "2026-03-10T10:12:45Z",
    "event_id": "c5e46g35-ce58-4808-b1g9-3246g4c357c9",
    "message": "Database connection timeout",
    "exception": { "Error type": "DB:TIMEOUT" }
  },
  {
    "timestamp": "2026-03-10T10:18:22Z",
    "event_id": "b4d35f24-bd47-4797-a0f8-2135f3b246b8",  ← SAME ID
    "message": "Failed to create referral",
    "exception": { "Error type": "EXT:CANT_CREATE_REFERRAL" }
  },
  {
    "timestamp": "2026-03-10T10:25:33Z",
    "event_id": "d6f57h46-df69-4919-c2h0-4357h5d468d0",
    "message": "Service unavailable",
    "exception": { "Error type": "SERVICE:UNAVAILABLE" }
  }
]
```

### Processing Steps

1. **Apply Filters** (time range, valid IDs)
   - Result: 5 errors (all pass filtering)

2. **Group by Correlation ID**
   ```javascript
   groupLogsByCorrelationId(filteredLogs)
   ```
   - Group 1: b4d35f24-bd47-4797-a0f8-2135f3b246b8 → 3 errors
   - Group 2: c5e46g35-ce58-4808-b1g9-3246g4c357c9 → 1 error
   - Group 3: d6f57h46-df69-4919-c2h0-4357h5d468d0 → 1 error

3. **Sort by Timestamp**
   - Card #1: First occurrence at 10:00:00
   - Card #2: First occurrence at 10:12:45
   - Card #3: First occurrence at 10:25:33

4. **Generate HTML**
   - 3 error cards (instead of 5)

### Output (Dashboard Display)

```
┌─────────────────────────────────────────────────────────┐
│  ⚠️  Manage Service Agent                                │
│  3 issues (5 total occurrences)                          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  #1                    [3 occurrences]         10:00:00  │
├─────────────────────────────────────────────────────────┤
│  API:                 job-app1                           │
│  Error Type:          EXT:CANT_CREATE_REFERRAL           │
│  File:                create-referral.xml                │
│  Correlation ID:      b4d35f24-bd47-4797-...             │
└─────────────────────────────────────────────────────────┘
│  ↓ View all 3 occurrences                               │
│    • #1 - Mar 10, 2026, 10:00:00                        │
│    • #2 - Mar 10, 2026, 10:05:12                        │
│    • #3 - Mar 10, 2026, 10:18:22                        │
├─────────────────────────────────────────────────────────┤
│  Error Summary                                           │
│  Analyzing error...                                     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  #2                    [1 occurrence]          10:12:45  │
├─────────────────────────────────────────────────────────┤
│  API:                 job-app1                           │
│  Error Type:          DB:TIMEOUT                         │
│  File:                api.xml                            │
│  Correlation ID:      c5e46g35-ce58-4808-...             │
├─────────────────────────────────────────────────────────┤
│  Error Summary                                           │
│  Analyzing error...                                     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  #3                    [1 occurrence]          10:25:33  │
├─────────────────────────────────────────────────────────┤
│  API:                 job-app1                           │
│  Error Type:          SERVICE:UNAVAILABLE                │
│  File:                main.xml                           │
│  Correlation ID:      d6f57h46-df69-4919-...             │
├─────────────────────────────────────────────────────────┤
│  Error Summary                                           │
│  Analyzing error...                                     │
└─────────────────────────────────────────────────────────┘
```

### Benefits in This Example

| Aspect | Before | After | Benefit |
|--------|--------|-------|---------|
| Cards Shown | 5 | 3 | 40% fewer cards |
| Scrolling | More scrolling needed | Less scrolling | Cleaner view |
| AI Summaries | 5 generated | 3 generated | 40% fewer API calls |
| Pattern Recognition | Hidden | Visible (3 same error) | Better insight |

---

## Example 2: All Errors Have Same Correlation ID

### Scenario
All 10 errors in log file happen during same transaction (same correlation ID).

### Before Implementation
```
❌ Error #1 - ID: abc-123
❌ Error #2 - ID: abc-123
❌ Error #3 - ID: abc-123
❌ Error #4 - ID: abc-123
❌ Error #5 - ID: abc-123
❌ Error #6 - ID: abc-123
❌ Error #7 - ID: abc-123
❌ Error #8 - ID: abc-123
❌ Error #9 - ID: abc-123
❌ Error #10 - ID: abc-123

↳ User has to scroll through 10 identical cards
↳ 10 AI summaries generated for same transaction
↳ Hard to see pattern - all look like separate issues
```

### After Grouping
```
⚠️ Manage Service Agent
1 issue (10 total occurrences)

┌──────────────────────────────────────┐
│ #1                [10 occurrences]    │
├──────────────────────────────────────┤
│ Correlation ID: abc-123              │
│ ↓ View all 10 occurrences            │
│   • #1 - 10:00:00                    │
│   • #2 - 10:00:15                    │
│   • #3 - 10:00:30                    │
│   ... (7 more)                       │
│   • #10 - 10:02:15                   │
├──────────────────────────────────────┤
│ Error Summary                        │
│ Single-transaction failure...        │
└──────────────────────────────────────┘

✅ Single card
✅ Single AI summary
✅ Clear that it's a cascading failure
✅ Easy to see error pattern (10 in 2 minutes)
```

### Key Insight
User can immediately see this is a **single transaction failure** causing 10 cascade errors, not 10 separate issues. This is critical for troubleshooting!

---

## Example 3: Mixed Duplicates and Unique Errors

### Scenario: Complex Multi-System Failure

```
Correlation IDs:
- trans-001: 4 errors (referral service cascade failure)
- trans-002: 2 errors (database timeout retry)
- trans-001: (duplicate, already grouped)
- trans-003: 1 error (manual API call failed)
- trans-001: (duplicate, already grouped)
- trans-004: 3 errors (auth service issues)
- trans-002: (duplicate, already grouped)
```

### Dashboard Result

```
⚠️ Manage Service Agent
4 issues (10 total occurrences)

Issue #1: trans-001 [4 occurrences] - Referral Service Failure
  • Timestamps show consecutive failures (cascade)
  • All errors: EXT:CANT_CREATE_REFERRAL
  
Issue #2: trans-004 [3 occurrences] - Auth Service Issues
  • Timestamps show intermittent failures (pattern)
  • Mix of AUTH:INVALID_TOKEN and AUTH:SERVICE_DOWN
  
Issue #3: trans-002 [2 occurrences] - Database Timeout
  • Timestamps close together (retry scenario)
  • Both: DB:CONNECTION_TIMEOUT
  
Issue #4: trans-003 [1 occurrence] - Manual API Call
  • Single occurrence
  • API:BAD_REQUEST
```

### Analysis Made Possible

By grouping, user can now:

1. **Identify Root Cause**
   - trans-001: Cascade failure (4 in sequence)
   - trans-004: Flaky service (3 intermittent)
   - trans-002: Retry scenario (2 close together)
   - trans-003: One-off issue

2. **Prioritize Fix**
   - Fix trans-001 cascade (fixes 4 errors)
   - Fix trans-004 flakiness (fixes 3 errors)
   - Fix trans-002 timeout (fixes 2 errors)
   - trans-003 might be user error

3. **Detect Patterns**
   - Service reliability issues (trans-004)
   - Infrastructure problems (trans-002)
   - Logic issues (trans-001)

**Without grouping**, all these patterns would be hidden in 10 individual cards!

---

## Implementation Details

### Grouping Algorithm

```javascript
// 1. Input: 10 logs with various correlation IDs
// 2. Create map: { "trans-001": [...], "trans-002": [...], ... }
// 3. Count occurrences in each group
// 4. Sort groups by first occurrence timestamp
// 5. Output: 4 groups (with counts and original indices)
```

### Display Logic

```javascript
// For each group:
// - Show first log as primary display
// - If errorCount > 1:
//   - Add count badge
//   - Add expandable occurrences list
//   - Show all timestamps
// - Generate single AI summary for group
```

### Interaction Flow

```
User views dashboard with 10 errors
           ↓
[Group By Correlation ID]
           ↓
4 unique error cards displayed
           ↓
User notices one card has [4 occurrences]
           ↓
User clicks "↓ View all 4 occurrences"
           ↓
Card expands to show all 4 timestamps
           ↓
User sees pattern (consecutive failures)
           ↓
User understands: "This is a cascade failure"
```

---

## Summary

The grouping feature transforms the error dashboard from:

❌ **Before**: Overwhelming list of duplicate cards
✅ **After**: Clear, organized view of distinct issues

This enables:
- Faster problem identification
- Better pattern recognition
- Reduced noise in the dashboard
- More focused troubleshooting
- Better resource allocation for fixes
