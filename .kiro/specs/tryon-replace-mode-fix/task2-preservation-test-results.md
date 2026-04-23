# Task 2: Preservation Property Tests - Results

## Test Execution Date
2026-04-22

## Test File
`backend/tests/test_tryon_replace_mode_preservation.py`

## Test Results on UNFIXED Code

### Summary
✅ **ALL 5 PRESERVATION TESTS PASSED**

This confirms the baseline behavior that must be preserved after implementing the fix.

### Individual Test Results

#### 1. test_preservation_non_replace_modes_use_pipeline_a
- **Status**: ✅ PASSED
- **Property**: For mode="strict" or mode="balanced", code uses pipeline A (run_pipeline_a)
- **Validates**: Requirement 3.1
- **Generated Examples**: 10 (property-based test with Hypothesis)
- **Observation**: All non-replace modes correctly call run_pipeline_a and return pipeline="A" responses

#### 2. test_preservation_bailian_not_configured_skips_bailian
- **Status**: ✅ PASSED
- **Property**: When Bailian not configured, code skips Bailian and tries remote VTON
- **Validates**: Requirement 3.2
- **Observation**: When _bailian_configured() returns False, call_bailian_tryon returns None and remote VTON is called

#### 3. test_preservation_bailian_success_returns_result
- **Status**: ✅ PASSED
- **Property**: When Bailian succeeds, code saves result image and returns success response
- **Validates**: Requirement 3.6
- **Generated Examples**: 10 (property-based test with Hypothesis)
- **Observation**: Successful Bailian responses result in HTTP 200 with result_image_url in /uploads/ path

#### 4. test_preservation_fallback_to_remote_vton_when_bailian_fails
- **Status**: ✅ PASSED
- **Property**: When Bailian fails and remote VTON configured, code falls back to remote VTON
- **Validates**: Requirement 3.3
- **Observation**: Bailian failure triggers call_remote_vton, which returns success and HTTP 200

#### 5. test_preservation_fallback_to_local_diffusion_when_all_fail
- **Status**: ✅ PASSED
- **Property**: When both Bailian and remote VTON fail with TRYON_V2_REPLACE_ALLOW_LOCAL_DIFFUSION=true, code falls back to local diffusion
- **Validates**: Requirement 3.4
- **Observation**: With both upstreams failing and local diffusion enabled, get_tryon_service().tryon_garment is called and returns success

## Conclusion

All preservation tests PASS on the unfixed code, confirming the baseline behavior patterns:

1. **Non-replace modes** (strict/balanced) use pipeline A unchanged
2. **Bailian not configured** skips Bailian and tries remote VTON unchanged
3. **Bailian success** saves image and returns success response unchanged
4. **Fallback to remote VTON** when Bailian fails is invoked unchanged
5. **Fallback to local diffusion** when both fail (with flag enabled) is invoked unchanged

These tests will be re-run after implementing the fix (Task 3) to verify no regressions were introduced.

## Next Steps

- Proceed to Task 3: Implement the fix for Bailian error diagnostics
- After fix implementation, re-run these preservation tests to verify they still PASS
- Re-run bug condition exploration tests (Task 1) to verify they now PASS (bug is fixed)
