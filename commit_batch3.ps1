# Commit script for batch 3
cd "d:\Users\omen\OneDrive\桌面\clothing-assistant"

echo "=== Checking git status ==="
git status --short

echo ""
echo "=== Staging files ==="
git add backend/app/services/finetuned_infer_client.py backend/app/core/config.py
echo "Files staged"

echo ""
echo "=== Creating commit ==="
git config user.email "dev@example.com"
git config user.name "Developer"
git commit -m "feat(inference): add fine-tuned model inference client with config"

echo ""
echo "=== Pushing to remote ==="
git push origin HEAD

echo ""
echo "=== Final status ==="
git log --oneline -2
