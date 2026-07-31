#!/bin/bash

source venv/bin/activate

echo "===== AI Startup ====="

echo
echo "=== START HERE ==="
head -40 instructions/START_HERE.md

echo
echo "=== CURRENT STATE ==="
head -60 docs/CURRENT_STATE.md

echo
echo "=== ROADMAP ==="
head -80 instructions/ROADMAP.md

echo
echo "=== AI RULES ==="
head -120 instructions/AI_RULES.md

echo
git status --short

echo
echo "Startup complete."