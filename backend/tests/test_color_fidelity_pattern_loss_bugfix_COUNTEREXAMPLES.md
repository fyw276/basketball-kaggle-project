# Bug Condition Exploration - Counterexamples Found

## Test: test_bug_condition_warped_layer_preserves_color_information

**Status**: FAILED (as expected - confirms bug exists)

**Date**: 2026-05-15

## Summary

The property-based test successfully confirmed the bug exists by generating multiple counterexamples showing that `warped_layer` RGB values are extremely low (< 20) for patterned garments, instead of preserving the original garment colors.

## Key Findings

### Warped Layer RGB Statistics (from logs)

Multiple test runs showed consistent failures with warped_layer having extremely low RGB values:

1. **Run 1**: R mean=6.43, G mean=9.51, B mean=15.88, A mean=17.08
   - Pattern: cartoon
   - Original garment RGB mean: ~147.58
   - Result: Nearly black warped_layer

2. **Run 2**: R mean=12.83, G mean=8.38, B mean=8.12, A mean=14.12
   - Pattern: stripes
   - Result: Nearly black warped_layer

3. **Run 3**: R mean=12.70, G mean=8.35, B mean=8.11, A mean=14.06
   - Pattern: checkerboard
   - Result: Nearly black warped_layer

4. **Run 4**: R mean=2.79, G mean=8.41, B mean=8.11, A mean=14.06
   - Pattern: cartoon
   - Result: Nearly black warped_layer (R channel extremely low at 2.79!)

5. **Run 5**: R mean=10.02, G mean=8.69, B mean=10.06, A mean=16.34
   - Pattern: embroidery
   - Result: Nearly black warped_layer

### Falsifying Example

```python
test_bug_condition_warped_layer_preserves_color_information(
    garment_data={
        'garment': <PIL.Image.Image image mode=RGB size=256x256>,
        'pattern_type': 'cartoon',
        'pattern_score': 0.7035462188720704,
        'color_variance': 936.1299845377604
    }
)
```

**Assertion Failure**:
```
Bug detected: Result RGB mean is 152.14, but original garment RGB mean is 56.45
(difference: 95.69, tolerance: 11.29).
Pattern type: cartoon, pattern_score=0.704, color_variance=936.13.
Expected result to preserve original colors within 20% tolerance.
```

## Analysis

### Bug Confirmation

The test successfully confirmed the bug exists:

1. **Warped Layer is Nearly Black**: All test runs showed warped_layer RGB values < 20, confirming the bug described in the design document.

2. **Affects All Pattern Types**: The bug affects all pattern types tested:
   - Checkerboard patterns
   - Horizontal stripes
   - Colorful stars
   - Cartoon characters
   - Embroidery patterns

3. **Alpha Channel Also Low**: The alpha channel values are also extremely low (14-17), suggesting the issue may be related to alpha channel handling during the warp/scale/paste pipeline.

### Root Cause Indicators

Based on the debug logs, the issue occurs during the warp/scale/paste pipeline in `catvton_color_fidelity_spatial`:

1. **After Scaling**: The garment is scaled using `Image.Resampling.LANCZOS`
2. **After Paste**: The `warped_layer` shows extremely low RGB values
3. **Realism Pass Applied**: The realism pass is applied even though pattern_score is low (< 0.40 threshold)

The logs show:
```
catvton_color_fidelity_spatial: proportional stretch-to-fill
(target=201x131, garment=44x87, scale=4.568 → scaled=201x397,
body_center=(254,325), gar_region=[154,260,355,391])

catvton_color_fidelity_spatial: warped_layer stats -
R mean=6.43, G mean=9.51, B mean=15.88, A mean=17.08,
R min/max=[0,117], G min/max=[0,183], B min/max=[0,255]
```

This suggests the problem occurs during:
- The scaling operation (LANCZOS resampling on RGBA may cause premultiplied alpha effects)
- The paste operation (low alpha values may cause the paste to fail)
- The cutout operation (alpha channel may be incorrectly generated)

## Next Steps

1. **Implement Fix**: Proceed with the fix implementation as outlined in tasks 3.1-3.6
2. **Focus Areas**:
   - Investigate scaling operation (separate RGB and alpha channels before scaling)
   - Check alpha channel values after cutout
   - Verify paste operation uses correct alpha values
   - Check if feathering is over-reducing alpha values

3. **Validation**: After fix implementation, re-run this test. It should PASS, confirming the bug is fixed.

## Test File Location

`backend/tests/test_color_fidelity_pattern_loss_bugfix.py`

## Related Files

- `backend/app/services/tryon_v2/warp_engine.py` (line 2042: `catvton_color_fidelity_spatial`)
- `backend/app/services/tryon_v2/garment_struct.py` (line 342: `cutout_garment_rgba`)
