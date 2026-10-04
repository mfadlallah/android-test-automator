#!/bin/bash
# Don't exit on first failure - we want to run all tests and report results

echo "🔧 Pre-flight checks..."
echo ""

# Check if OCR tool exists and is executable
if [ ! -x "tools/screen_ocr" ]; then
  echo "⚙️  Compiling OCR tool (screen_ocr)..."

  if [ ! -f "tools/screen_ocr.swift" ]; then
    echo "❌ ERROR: tools/screen_ocr.swift not found!"
    exit 1
  fi

  xcrun swiftc \
    -framework Vision \
    -framework Foundation \
    -framework ImageIO \
    tools/screen_ocr.swift \
    -o tools/screen_ocr

  chmod +x tools/screen_ocr
  echo "✅ OCR tool compiled successfully"
else
  echo "✅ OCR tool found and executable"
fi

echo ""
echo "🚀 Running all test cases..."
total=0
passed=0
failed_cases=()

for case in cases/*.txt; do
  ((total++))
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "Test $total: $(basename $case)"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "⏱️  Starting test (timeout: 15 minutes)..."
  echo ""

  if timeout 900 python3 -m src.main --case "$case"; then
    ((passed++))
    echo ""
    echo "✅ PASSED: $(basename $case)"
  else
    exit_code=$?
    if [ $exit_code -eq 124 ]; then
      echo "❌ TIMEOUT: $(basename $case) exceeded 15 minutes"
    else
      echo "❌ FAILED: $(basename $case) (exit code: $exit_code)"
    fi
    failed_cases+=("$(basename $case)")
  fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Results: $passed/$total tests passed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ ${#failed_cases[@]} -gt 0 ]; then
  echo ""
  echo "❌ Failed tests:"
  for case in "${failed_cases[@]}"; do
    echo "  - $case"
  done
  exit 1
else
  echo ""
  echo "🎉 All tests passed!"
  exit 0
fi
