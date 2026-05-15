# Color Fidelity Pattern Loss - Root Cause Diagnosis

## Task 3.1 Diagnosis Results

### Debug Logging Analysis

Added detailed debug logging at each step in the `catvton_color_fidelity_spatial` pipeline:

1. **After `cutout_garment_rgba`**: RGB mean=160.36, Alpha mean=255.00 ✅
2. **After scaling (`gar_src.resize()`)**: RGB mean=159.83, Alpha mean=255.00 ✅
3. **After paste (`warped_layer.paste()`)**: RGB mean=158.41, Alpha mean=255.00 ✅
4. **After feathering (`_feather_alpha()`)**: RGB mean=158.93, Alpha mean=240.28 ✅
5. **After face/hand protection**:
   - RGB mean in non-transparent regions (alpha>128): 158.93 ✅
   - Alpha mean in non-transparent regions (alpha>128): 240.28 ✅
   - **RGB mean for ALL pixels: 10.61 ❌**
   - **Alpha mean for ALL pixels: 17.08 ❌**
6. **Final warped_layer stats** (logged at line 2463): R mean=6.43, G mean=9.51, B mean=15.88, A mean=17.08 ❌

### Root Cause Identified

**The color loss occurs in the face/hand protection step (lines 2427-2453).**

The protection mask is being applied too aggressively, setting most of the warped_layer to transparent (alpha=0). This leaves only a tiny region with the garment visible, which explains why the overall RGB mean drops to ~10 (most pixels are black/transparent).

### Detailed Analysis

The face/hand protection logic works as follows:

1. Creates a protection mask where:
   - 0 = protected (face/hands, should NOT show garment)
   - 255 = allow garment
2. Multiplies the warped_layer's alpha channel by this protection mask
3. This sets alpha=0 for protected regions

**The problem**: The protection mask is incorrectly marking most of the image as "protected" (value=0), when it should only protect small face/hand regions.

Looking at the code:
- `_make_face_protect_mask()` creates the mask
- If no face is detected by Haar cascade, it falls back to coarse neck-based protection
- The fallback logic uses `protect_until_y = max(0, int(neck_y - ch * 0.06))` and then `protect_mask.paste(0, (0, 0, cw, protect_until_y))`
- This protects the entire top portion of the image from y=0 to neck_y

**The bug**: When no face is detected (which is common with synthetic test images), the fallback protection is too aggressive and protects a large portion of the image, including the garment region.

### Specific Problem

The debug logs show:
```
DEBUG    app.services.tryon_v2.warp_engine:warp_engine.py:254 catvton_color_fidelity_spatial: no face detected by Haar cascade (will use coarse neck-based protection)
```

This means the Haar cascade failed to detect a face, so the code fell back to the coarse neck-based protection. However, this fallback is protecting too much of the image.

Looking at the garment region: `gar_region=[154,260,355,391]`
- Garment starts at y=260
- neck_y is likely around 260 (based on the garment region)
- `protect_until_y = max(0, int(neck_y - ch * 0.06))` = max(0, int(260 - 512*0.06)) = max(0, 229)
- So the protection mask protects from y=0 to y=229

But wait, the garment starts at y=260, so this should be fine. Let me check the hand protection logic...

Actually, looking more carefully at the code, I see that the protection mask is initialized with `color=255` (allow garment everywhere), and then specific regions are set to 0 (protected). So the logic should be correct.

**The real issue**: The protection mask is being applied AFTER the paste operation, but the paste operation only placed the garment in a specific region (gar_region=[154,260,355,391]). The rest of the image is already transparent (alpha=0). When we multiply the alpha channel by the protection mask, we're not changing much because most of the image is already transparent.

Wait, that doesn't explain why the RGB mean drops from 158.93 to 10.61...

Let me re-examine the logs:
- After feathering: RGB mean=158.93 (in non-transparent regions, alpha>128)
- After face/hand protection: RGB mean=158.93 (in non-transparent regions, alpha>128)
- After face/hand protection: RGB mean=10.61 (ALL pixels)

This makes sense! The RGB values in the non-transparent regions are still correct (158.93), but when we average over ALL pixels (including the transparent ones with RGB=0), the mean drops to 10.61.

**The actual problem**: The existing log at line 2463 (which shows R mean=6.43, G mean=9.51, B mean=15.88) is calculating the mean over ALL pixels, not just non-transparent regions. This is misleading because it includes all the transparent pixels (which have RGB=0).

But wait, the test is failing because the final result has the wrong colors. Let me check what the test is actually measuring...

Looking at the test code, it's measuring the RGB mean of the final result image (after all processing), not the warped_layer. So the issue is that the warped_layer has very low alpha values overall (mean=17.08), which means it has almost no effect on the final result during the blending step.

### Revised Root Cause

The problem is that **the warped_layer has very low alpha values overall** (mean=17.08), which means:

1. During the blending step (lines 2456-2472), `strength = layer_alpha * fidelity_strength` is very low
2. This means the warped_layer has almost no effect on the final result
3. The final result is mostly the original catvton_result, with very little contribution from the warped_layer

The low alpha values are caused by:
1. The warped_layer is only pasted in a small region (gar_region=[154,260,355,391])
2. The rest of the image is transparent (alpha=0)
3. The face/hand protection further reduces the alpha in some regions
4. Overall, most of the image has alpha=0, so the mean alpha is very low (17.08)

**The fix**: The issue is not with the face/hand protection logic itself, but with how the warped_layer is being used. The warped_layer should only contain the garment region, and the blending should only happen in that region. Currently, the blending is happening over the entire image, which dilutes the effect.

Actually, looking at the blending code more carefully:
```python
layer_alpha = layer_np[:, :, 3] / 255.0
strength = layer_alpha * fidelity_strength

for c in range(3):
    result_np[:, :, c] = layer_np[:, :, c] * strength + result_np[:, :, c] * (1.0 - strength)
```

This is correct! The blending uses `layer_alpha` as a per-pixel weight, so pixels with alpha=0 will have strength=0 and won't be affected. Pixels with alpha=255 will have strength=fidelity_strength (0.75) and will be blended.

So the blending logic is correct. The problem must be elsewhere...

Let me re-read the test failure message:
```
AssertionError: Bug detected: Result RGB mean is 152.14, but original garment RGB mean is 56.45 (difference: 95.69, tolerance: 11.29).
```

Wait, the result RGB mean (152.14) is HIGHER than the original garment RGB mean (56.45)! This means the result is too bright, not too dark. This is the opposite of what I expected based on the "warped_layer RGB mean < 20" bug description.

Let me check the test code to understand what it's measuring...

Actually, I think I misunderstood the bug. The bug description says "warped_layer RGB mean < 20", but the test is measuring the final result RGB mean, not the warped_layer RGB mean. The test is checking that the final result preserves the original garment colors.

In this case:
- Original garment RGB mean: 56.45 (dark colors)
- Final result RGB mean: 152.14 (bright colors)
- The result is too bright, meaning the original garment colors were NOT preserved

This makes sense! The warped_layer has very low alpha values (mean=17.08), so it has almost no effect on the final result. The final result is mostly the original catvton_result (which is bright), with very little contribution from the warped_layer (which should have the dark garment colors).

### Final Root Cause

**The warped_layer has very low alpha values overall (mean=17.08) because:**

1. The warped_layer is only pasted in a small region (gar_region=[154,260,355,391])
2. The rest of the image is transparent (alpha=0)
3. When we calculate the mean alpha over the entire image, it's very low (17.08)

**This causes the final result to not preserve the original garment colors because:**

1. During blending, `strength = layer_alpha * fidelity_strength` is very low for most pixels
2. The final result is mostly the original catvton_result, with very little contribution from the warped_layer
3. The original garment colors are not preserved

**The fix should focus on:**

1. Ensuring the warped_layer has sufficient alpha values in the garment region
2. Investigating why the garment region is so small (only 201x131 pixels out of 512x768 image)
3. Checking if the paste operation is working correctly
4. Verifying that the TPS warp (if applied) is not reducing the alpha values

### Next Steps for Task 3.2-3.6

Based on this diagnosis, the fix should:

1. **Task 3.2**: Investigate the scaling operation - ensure it preserves alpha values
2. **Task 3.3**: Investigate the TPS warp - ensure it preserves alpha values (note: TPS was NOT applied in this test run)
3. **Task 3.4**: Investigate the cutout and paste operations - ensure alpha values are sufficient
4. **Task 3.5**: Investigate the feathering operation - ensure it doesn't over-reduce alpha values
5. **Task 3.6**: Add validation and fallback mechanism

The key insight is that the alpha values are being lost somewhere in the pipeline, causing the warped_layer to have almost no effect on the final result.
