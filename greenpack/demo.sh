#!/bin/bash
echo "=== Step 1: Submit Declaration ==="
curl -s -X POST http://localhost:8000/submit \
-H "Content-Type: application/json" \
-d '{
  "producer_id": "GREENPACK-001",
  "month": "2026-04",
  "declared_quantities_kg": {
    "rigid_plastic": 12000,
    "flexible_plastic": 8500,
    "multilayer_plastic": 3200
  }
}' | python3 -m json.tool

echo ""
echo "=== Step 2: Get Summary ==="
curl -s http://localhost:8000/summary/GREENPACK-001/2026-04 \
| python3 -m json.tool

echo ""
echo "=== Step 3: Ask EPR Question ==="
curl -s -X POST http://localhost:8000/ask \
-H "Content-Type: application/json" \
-d '{"question": "What is the deadline for monthly declaration?"}' \
| python3 -m json.tool
