import sys

sys.path.insert(0, r"D:\Users\omen\OneDrive\桌面\clothing-assistant\backend")

print("=== Testing sam_mask ===")
from app.services.sam_mask import MobileSAMWrapper, sam_segment_garment

print("OK: sam_mask")

print()
print("=== Testing human_parsing ===")
from app.services.human_parsing import SCHPParser, schp_parse

print("OK: human_parsing")

print()
print("=== Testing cloth_warp ===")
from app.services.cloth_warp import TPSWarpEngine, tps_warp_garment

print("OK: cloth_warp")

print()
print("=== Testing garment_classifier ===")
from app.services.garment_classifier import GarmentClassifier, classify_garment

print("OK: garment_classifier")

print()
print("ALL IMPORTS OK")
