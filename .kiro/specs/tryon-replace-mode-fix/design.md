# Try-On Replace Mode Fix - Bugfix Design

## Overview

The virtual try-on "replace" mode fails with HTTP 503 error even when Bailian (DashScope) is properly configured (`DASHSCOPE_TRYON_ENABLED=true` and `DASHSCOPE_API_KEY` set). The bug occurs because the error handling logic in `backend/app/api/tryon_v2.py` does not provide detailed diagnostic information when Bailian API calls fail, making it impossible for users to identify the root cause (invalid API key, quota exhaustion, model permission issues, network errors, etc.).

The fix will enhance error diagnostics by capturing detailed error information from Bailian API responses and exceptions, then surfacing this information in the HTTP 503 error response's `replace_debug.bailian` field and `action_hint` message. This will enable users to quickly identify and resolve configuration issues without guessing.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug - when replace mode is selected with Bailian configured but API calls fail without detailed diagnostics
- **Property (P)**: The desired behavior when Bailian API fails - detailed error diagnostics in response including status, message, reason, error_type, and specific_hint
- **Preservation**: Existing behavior for strict/balanced modes, fallback logic to remote VTON and local diffusion, and successful Bailian responses must remain unchanged
- **call_bailian_tryon**: The async function in `backend/app/services/bailian_tryon_client.py` that calls Bailian API and returns a dict with status, message, result_image, and metadata
- **tryon_garment_v2**: The FastAPI endpoint in `backend/app/api/tryon_v2.py` that handles mode="replace" requests and processes Bailian responses
- **replace_debug**: The diagnostic field in HTTP 503 error responses containing bailian and remote sub-objects with detailed error information
- **bailian_diag**: The diagnostic dict populated when Bailian is configured but fails, containing configured, status, message, reason, error_type, and specific_hint fields
- **_bailian_configured()**: Helper function that returns True if `DASHSCOPE_TRYON_ENABLED=true` and `DASHSCOPE_API_KEY` is set

## Bug Details

### Bug Condition

The bug manifests when a user selects mode="replace" and Bailian is properly configured (`DASHSCOPE_TRYON_ENABLED=true` and `DASHSCOPE_API_KEY` set), but the Bailian API call returns an error status (status != "success" or result_image is None). The `tryon_garment_v2` function in `backend/app/api/tryon_v2.py` checks if Bailian is configured, but when the API call fails, it does not extract detailed diagnostic information from the response's metadata field, resulting in empty or incomplete `bailian_diag` and generic error hints.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type TryOnRequest (mode, garment_bytes, person_bytes, config)
  OUTPUT: boolean

  RETURN input.mode == "replace"
         AND _bailian_configured() == True
         AND (upstream.status != "success" OR upstream.result_image is None)
         AND bailian_diag is empty or missing detailed error fields
END FUNCTION
```

### Examples

- **Example 1 - Invalid API Key**: User sets `DASHSCOPE_API_KEY="invalid-key-12345"` and `DASHSCOPE_TRYON_ENABLED=true`, then calls `/api/v2/tryon/garment` with mode="replace". Bailian API returns error with code "InvalidApiKey". Current behavior: HTTP 503 with generic hint "百炼失败：未知错误；查看 detail.replace_debug.bailian 获取详情" and empty `bailian_diag`. Expected behavior: HTTP 503 with specific hint "百炼失败：API key 无效或已过期（InvalidApiKey）" and `bailian_diag` containing status="error", message="InvalidApiKey", reason="dashscope_http", error_type="api_error", specific_hint="API key 无效或已过期", status_code=401.

- **Example 2 - Quota Exhausted**: User has valid API key but exhausted quota. Bailian API returns error with code "QuotaExceeded". Current behavior: HTTP 503 with generic hint. Expected behavior: HTTP 503 with specific hint "百炼失败：API 额度不足或超出限制（QuotaExceeded）" and detailed `bailian_diag`.

- **Example 3 - Network Timeout**: Network connection to Bailian API times out, raising `httpx.TimeoutException`. Current behavior: HTTP 503 with generic hint "百炼失败：未知错误" and empty `bailian_diag`. Expected behavior: HTTP 503 with specific hint "百炼失败：网络超时（TimeoutException）" and `bailian_diag` containing exception_message, error_type="TimeoutException", specific_hint="网络超时".

- **Edge Case - Success but No Image**: Bailian API returns status="success" but result_image is None. Expected behavior: HTTP 503 with specific hint "百炼返回成功但缺少结果图" and `bailian_diag` containing reason="dashscope_no_url" or similar.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Strict and balanced modes must continue to use pipeline A (run_pipeline_a) without any changes to their logic or error handling
- When Bailian is not configured (`DASHSCOPE_TRYON_ENABLED=false` or `DASHSCOPE_API_KEY` not set), the system must continue to skip Bailian and try remote VTON or local diffusion as before
- When Bailian API call succeeds (status="success" and result_image is not None), the system must continue to save the result image and return success response exactly as before
- The fallback logic to remote VTON when Bailian fails must remain unchanged (call_remote_vton is invoked, remote_ok is checked)
- The fallback logic to local diffusion when both Bailian and remote VTON fail and `TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION=true` must remain unchanged
- The `/tryon/validate-input` endpoint must continue to skip pipeline A input gate for mode="replace" and return pass status

**Scope:**
All inputs that do NOT involve mode="replace" with Bailian configured and failing should be completely unaffected by this fix. This includes:
- mode="strict" or mode="balanced" requests (use pipeline A)
- mode="replace" requests when Bailian is not configured (skip to remote VTON or local diffusion)
- mode="replace" requests when Bailian succeeds (return success response)
- All other endpoints like `/tryon/preprocess`, `/tryon/preprocess-batch`, `/tryon/pants`

## Hypothesized Root Cause

Based on the bug description and code analysis, the most likely issues are:

1. **Incomplete Error Extraction**: The `tryon_garment_v2` function in `backend/app/api/tryon_v2.py` (lines 450-490) checks if `upstream` is a dict and extracts `message` and `metadata.reason`, but does not extract all available diagnostic fields like `metadata.error_type`, `metadata.specific_hint`, `metadata.status_code`, `metadata.code`, `metadata.exception_message`. This results in incomplete `bailian_diag` even when `call_bailian_tryon` returns detailed error information.

2. **Generic Error Hints**: The error hint construction logic (lines 470-480) only checks for `reason == "dashscope_missing"` and falls back to generic hints like "百炼失败：{reason or '未知错误'}" without using the `specific_hint` field that `call_bailian_tryon` already provides in metadata.

3. **Missing Exception Handling**: The `call_bailian_tryon` function in `backend/app/services/bailian_tryon_client.py` catches exceptions and returns error dicts with metadata, but the calling code in `tryon_garment_v2` does not handle the case where `upstream` is None (when Bailian is not configured) vs. when `upstream` is a dict with error status (when Bailian is configured but failed).

4. **Insufficient Diagnostic Fields**: The `bailian_diag` dict construction (lines 460-468) only includes configured, status, message, reason, error_type, and specific_hint, but does not include other useful fields like status_code, code, exception_message, model, function that are available in the metadata returned by `call_bailian_tryon`.

## Correctness Properties

Property 1: Bug Condition - Detailed Bailian Error Diagnostics

_For any_ replace mode request where Bailian is configured (`_bailian_configured()` returns True) and the Bailian API call fails (status != "success" or result_image is None), the fixed `tryon_garment_v2` function SHALL return an HTTP 503 error response with a `replace_debug.bailian` field containing all available diagnostic information from the Bailian response metadata (status, message, reason, error_type, specific_hint, status_code, code, exception_message, model, function), and the `action_hint` SHALL include a specific error message derived from `specific_hint` or error analysis (e.g., "百炼失败：API key 无效或已过期" instead of "百炼失败：未知错误").

**Validates: Requirements 2.2, 2.3, 2.4, 2.5**

Property 2: Preservation - Non-Replace Mode Behavior

_For any_ request where mode is NOT "replace" (mode="strict" or mode="balanced"), the fixed code SHALL produce exactly the same behavior as the original code, using pipeline A (run_pipeline_a) and preserving all existing error handling and success response logic.

**Validates: Requirements 3.1**

Property 3: Preservation - Bailian Not Configured Behavior

_For any_ replace mode request where Bailian is NOT configured (`_bailian_configured()` returns False), the fixed code SHALL produce exactly the same behavior as the original code, skipping Bailian and attempting remote VTON or local diffusion fallback according to existing logic.

**Validates: Requirements 3.2**

Property 4: Preservation - Bailian Success Behavior

_For any_ replace mode request where Bailian API call succeeds (status="success" and result_image is not None), the fixed code SHALL produce exactly the same behavior as the original code, saving the result image to storage and returning a success response with result_image_url.

**Validates: Requirements 3.6**

Property 5: Preservation - Fallback Logic

_For any_ replace mode request where Bailian fails and remote VTON is configured, the fixed code SHALL continue to invoke `call_remote_vton` and check `remote_ok` exactly as before. When both Bailian and remote VTON fail and `TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION=true`, the fixed code SHALL continue to fall back to local diffusion.

**Validates: Requirements 3.3, 3.4**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `backend/app/api/tryon_v2.py`

**Function**: `tryon_garment_v2` (lines 450-490 in the replace mode error handling block)

**Specific Changes**:
1. **Extract All Diagnostic Fields**: When `upstream` is a dict with error status, extract all available fields from `upstream.get("metadata")` including error_type, specific_hint, status_code, code, exception_message, model, function, and include them in `bailian_diag`.
   - Current: Only extracts reason, specific_hint, error_type
   - Fixed: Extract status_code, code, exception_message, model, function as well

2. **Prioritize specific_hint in Error Hints**: When constructing error hints, check if `specific_hint` is available and non-empty first, then use it to construct a specific error message. Only fall back to generic hints if `specific_hint` is empty.
   - Current: Only checks `reason == "dashscope_missing"`, then falls back to generic hint
   - Fixed: Check `specific_hint` first, construct hint like "百炼失败：{specific_hint}（{msg}）" if available

3. **Handle All Error Scenarios**: Ensure `bailian_diag` is populated for all error scenarios including:
   - Bailian configured but returns error status (already partially handled)
   - Bailian configured but returns None (add check for `upstream is None` after `call_bailian_tryon`)
   - Bailian configured but raises exception (already handled in `call_bailian_tryon`, ensure metadata is extracted)
   - Bailian configured but returns success with no result_image (add specific check and diagnostic)

4. **Add Diagnostic Fields to bailian_diag**: Include all available metadata fields in `bailian_diag` to help users diagnose issues:
   - status_code (HTTP status code from DashScope API)
   - code (error code from DashScope API response)
   - exception_message (exception message if call_bailian_tryon caught an exception)
   - model (model ID used for the call)
   - function (function name used for the call)

5. **Improve Error Message Construction**: When `upstream` is not a dict or is None after Bailian is configured, add a specific diagnostic entry indicating "百炼失败：未返回有效响应" with reason="bailian_none_response".

**File**: `backend/app/services/bailian_tryon_client.py`

**Function**: `_call_bailian_tryon_sync` (no changes required, already returns detailed metadata)

**Verification**: The `_call_bailian_tryon_sync` function already returns detailed error metadata including reason, error_type, specific_hint, status_code, code, exception_message, model. No changes needed here. The fix is entirely in the calling code in `tryon_v2.py`.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code (lack of detailed diagnostics), then verify the fix provides detailed diagnostics and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm that when Bailian is configured but fails, the error response lacks detailed diagnostics. If we observe detailed diagnostics on unfixed code, we will need to re-hypothesize.

**Test Plan**: Write tests that mock `call_bailian_tryon` to return various error responses (invalid API key, quota exceeded, network timeout, success with no image), then call `tryon_garment_v2` with mode="replace" and assert that the HTTP 503 error response contains empty or incomplete `bailian_diag` and generic error hints. Run these tests on the UNFIXED code to observe failures and confirm the root cause.

**Test Cases**:
1. **Invalid API Key Test**: Mock `call_bailian_tryon` to return `{"status": "error", "message": "InvalidApiKey", "metadata": {"reason": "dashscope_http", "error_type": "api_error", "code": "InvalidApiKey", "status_code": 401, "specific_hint": "API key 无效或已过期"}}`. Call `tryon_garment_v2` with mode="replace". Assert HTTP 503 response has `bailian_diag` missing status_code, code, specific_hint fields, and action_hint is generic like "百炼失败：未知错误". (will fail on unfixed code - demonstrates bug)

2. **Quota Exceeded Test**: Mock `call_bailian_tryon` to return error with code="QuotaExceeded", specific_hint="API 额度不足或超出限制". Assert HTTP 503 response has incomplete `bailian_diag` and generic action_hint. (will fail on unfixed code)

3. **Network Timeout Test**: Mock `call_bailian_tryon` to return `{"status": "error", "message": "网络超时", "metadata": {"reason": "dashscope_exception", "error_type": "TimeoutException", "exception_message": "Request timed out", "specific_hint": "网络超时"}}`. Assert HTTP 503 response has `bailian_diag` missing exception_message and error_type fields. (will fail on unfixed code)

4. **Success with No Image Test**: Mock `call_bailian_tryon` to return `{"status": "success", "result_image": None, "metadata": {"reason": "dashscope_no_url", "model": "wanx2.1-imageedit"}}`. Assert HTTP 503 response has incomplete `bailian_diag` and generic action_hint. (will fail on unfixed code)

**Expected Counterexamples**:
- `bailian_diag` is missing fields like status_code, code, exception_message, model, function
- action_hint contains generic messages like "百炼失败：未知错误；查看 detail.replace_debug.bailian 获取详情" instead of specific hints like "百炼失败：API key 无效或已过期（InvalidApiKey）"
- Possible causes: incomplete error extraction, generic error hint construction, missing diagnostic fields

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds (replace mode with Bailian configured and failing), the fixed function produces detailed error diagnostics.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  response := tryon_garment_v2_fixed(input)
  ASSERT response.status_code == 503
  ASSERT response.detail.replace_debug.bailian is not empty
  ASSERT response.detail.replace_debug.bailian contains all available diagnostic fields
  ASSERT response.detail.action_hint contains specific error message (not generic)
END FOR
```

**Test Plan**: Write unit tests that mock `call_bailian_tryon` to return various error responses, then call the fixed `tryon_garment_v2` and assert that:
- HTTP 503 response contains `replace_debug.bailian` with all available fields (status, message, reason, error_type, specific_hint, status_code, code, exception_message, model, function)
- action_hint contains specific error message derived from specific_hint or error analysis
- All error scenarios are covered (invalid key, quota exceeded, network timeout, success with no image, None response)

**Test Cases**:
1. **Invalid API Key - Fixed**: Mock error response with all fields. Assert `bailian_diag` contains status_code=401, code="InvalidApiKey", specific_hint="API key 无效或已过期", and action_hint is "百炼失败：API key 无效或已过期（InvalidApiKey）".

2. **Quota Exceeded - Fixed**: Mock error response. Assert `bailian_diag` contains code="QuotaExceeded", specific_hint="API 额度不足或超出限制", and action_hint is specific.

3. **Network Timeout - Fixed**: Mock exception response. Assert `bailian_diag` contains error_type="TimeoutException", exception_message="Request timed out", specific_hint="网络超时", and action_hint is "百炼失败：网络超时（TimeoutException）".

4. **Success with No Image - Fixed**: Mock success response with result_image=None. Assert `bailian_diag` contains reason="dashscope_no_url", model="wanx2.1-imageedit", and action_hint mentions "百炼返回成功但缺少结果图".

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold (non-replace modes, Bailian not configured, Bailian succeeds), the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT tryon_garment_v2_original(input) = tryon_garment_v2_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for strict/balanced modes, Bailian not configured, and Bailian success scenarios, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Strict Mode Preservation**: Mock mode="strict" requests. Observe that unfixed code calls `run_pipeline_a` and returns pipeline A results. Write test to verify fixed code produces identical behavior (calls `run_pipeline_a`, returns same response structure).

2. **Balanced Mode Preservation**: Mock mode="balanced" requests. Observe that unfixed code calls `run_pipeline_a`. Write test to verify fixed code produces identical behavior.

3. **Bailian Not Configured Preservation**: Mock mode="replace" with `_bailian_configured()` returning False. Observe that unfixed code skips Bailian and tries remote VTON. Write test to verify fixed code produces identical behavior (skips Bailian, calls `call_remote_vton`).

4. **Bailian Success Preservation**: Mock mode="replace" with `call_bailian_tryon` returning success response with result_image. Observe that unfixed code saves image and returns success response. Write test to verify fixed code produces identical behavior (saves image, returns same response structure with result_image_url).

5. **Fallback Logic Preservation**: Mock mode="replace" with Bailian failing and remote VTON configured. Observe that unfixed code calls `call_remote_vton` and checks `remote_ok`. Write test to verify fixed code produces identical behavior (calls `call_remote_vton`, checks `remote_ok`, falls back to local diffusion if configured).

### Unit Tests

- Test error extraction logic: mock various error responses from `call_bailian_tryon` and verify all diagnostic fields are extracted into `bailian_diag`
- Test error hint construction: verify specific_hint is prioritized over generic hints
- Test edge cases: None response, success with no image, missing metadata fields
- Test preservation: verify strict/balanced modes, Bailian not configured, Bailian success scenarios produce identical behavior

### Property-Based Tests

- Generate random error responses with various combinations of metadata fields (status_code, code, exception_message, specific_hint) and verify fixed code extracts all available fields into `bailian_diag`
- Generate random mode values (strict, balanced, replace) and configuration states (_bailian_configured True/False) and verify preservation of existing behavior for non-buggy inputs
- Generate random Bailian success responses with result_image and verify fixed code produces identical success responses as unfixed code

### Integration Tests

- Test full replace mode flow with mocked Bailian API returning various error responses, verify HTTP 503 error contains detailed diagnostics
- Test full replace mode flow with Bailian success, verify success response is identical to unfixed code
- Test full replace mode flow with Bailian failure and remote VTON fallback, verify fallback logic is preserved
- Test strict/balanced mode flows, verify they are completely unaffected by the fix
