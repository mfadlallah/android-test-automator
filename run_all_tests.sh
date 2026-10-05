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
echo "📂 Creating artifacts folder for this run..."
# Create a single run folder for all test cases
RUN_FOLDER="artifacts/run-$(date +%Y%m%d-%H%M%S)-$(openssl rand -hex 3)"
mkdir -p "$RUN_FOLDER"
echo "✅ Run folder: $RUN_FOLDER"
echo ""

echo "🚀 Running all test cases..."
total=0
passed=0
failed_cases=()

for case in cases/*.txt; do
  ((total++))
  case_name=$(basename "$case" .txt)
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "Test $total: $case_name"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "⏱️  Starting test (timeout: 15 minutes)..."
  echo "📁 Artifacts: $RUN_FOLDER/$case_name"
  echo ""

  # Pass run folder to main.py via environment variable
  if timeout 900 env TEST_RUN_FOLDER="$RUN_FOLDER" TEST_CASE_NAME="$case_name" \
       python3 -m src.main --case "$case"; then
    ((passed++))
    echo ""
    echo "✅ PASSED: $case_name"
  else
    exit_code=$?
    if [ $exit_code -eq 124 ]; then
      echo "❌ TIMEOUT: $case_name exceeded 15 minutes"
    else
      echo "❌ FAILED: $case_name (exit code: $exit_code)"
    fi
    failed_cases+=("$case_name")
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
