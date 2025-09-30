#!/bin/bash
# Browser Service API Test Script
# ================================

set -e

# Configuration
BASE_URL="${BASE_URL:-http://localhost:8080}"
JWT_TOKEN="${JWT_TOKEN:-your-jwt-token-here}"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

log_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

test_endpoint() {
    local method=$1
    local endpoint=$2
    local data=$3
    local description=$4
    
    echo ""
    log_info "Testing: $description"
    echo "Endpoint: $method $endpoint"
    
    if [ -z "$data" ]; then
        response=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
            -X "$method" \
            -H "Authorization: Bearer $JWT_TOKEN" \
            "$BASE_URL$endpoint")
    else
        response=$(curl -s -w "\nHTTP_CODE:%{http_code}" \
            -X "$method" \
            -H "Authorization: Bearer $JWT_TOKEN" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "$BASE_URL$endpoint")
    fi
    
    http_code=$(echo "$response" | grep "HTTP_CODE:" | cut -d: -f2)
    body=$(echo "$response" | sed '/HTTP_CODE:/d')
    
    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        log_success "Response: $http_code"
        echo "$body" | python -m json.tool 2>/dev/null || echo "$body"
        return 0
    else
        log_error "Response: $http_code"
        echo "$body"
        return 1
    fi
}

# Check if JWT_TOKEN is set
if [ "$JWT_TOKEN" == "your-jwt-token-here" ]; then
    log_error "JWT_TOKEN not set. Please export JWT_TOKEN environment variable."
    echo "Usage: JWT_TOKEN=your-token ./test_api.sh"
    exit 1
fi

echo "======================================"
echo "Browser Service API Test Suite"
echo "======================================"
echo "Base URL: $BASE_URL"
echo ""

# Test 1: Health Checks (No Auth)
log_info "=== Testing Health Endpoints (No Auth) ==="

test_endpoint "GET" "/health/live" "" "Liveness Probe"
test_endpoint "GET" "/health/ready" "" "Readiness Probe"

# Test 2: Root Endpoint
log_info "=== Testing Root Endpoint ==="
test_endpoint "GET" "/" "" "Service Information"

# Test 3: Browser Health (With Auth)
log_info "=== Testing Browser Health (With Auth) ==="
test_endpoint "GET" "/health/browser" "" "Browser Health Check"

# Test 4: Create Session
log_info "=== Testing Session Management ==="
SESSION_DATA='{
  "session_type": "standard",
  "viewport_width": 1920,
  "viewport_height": 1080
}'
test_endpoint "POST" "/browser/session/create" "$SESSION_DATA" "Create Browser Session"

# Test 5: Get Session Info
test_endpoint "GET" "/browser/session/info" "" "Get Session Information"

# Test 6: Navigate
log_info "=== Testing Navigation ==="
NAV_DATA='{
  "url": "https://example.com",
  "wait_until": "networkidle",
  "timeout": 30000
}'
test_endpoint "POST" "/browser/navigate" "$NAV_DATA" "Navigate to URL"

# Test 7: Get Text
log_info "=== Testing Data Extraction ==="
test_endpoint "GET" "/browser/text?selector=h1&timeout=30000" "" "Extract Text from Element"

# Test 8: Screenshot
log_info "=== Testing Screenshot ==="
SCREENSHOT_DATA='{"full_page": false}'
echo ""
log_info "Capturing screenshot..."
curl -s \
    -X POST \
    -H "Authorization: Bearer $JWT_TOKEN" \
    -H "Content-Type: application/json" \
    -d "$SCREENSHOT_DATA" \
    "$BASE_URL/browser/screenshot" \
    --output test_screenshot.png

if [ -f test_screenshot.png ]; then
    size=$(stat -f%z test_screenshot.png 2>/dev/null || stat -c%s test_screenshot.png 2>/dev/null)
    if [ "$size" -gt 0 ]; then
        log_success "Screenshot saved: test_screenshot.png ($size bytes)"
    else
        log_error "Screenshot file is empty"
    fi
else
    log_error "Screenshot not saved"
fi

# Test 9: Fill Input
log_info "=== Testing Interactions ==="
FILL_DATA='{
  "selector": "input[name=\"q\"]",
  "value": "test search",
  "timeout": 30000
}'
test_endpoint "POST" "/browser/fill" "$FILL_DATA" "Fill Input Field" || true

# Test 10: Close Session
log_info "=== Testing Session Cleanup ==="
test_endpoint "DELETE" "/browser/session/close" "" "Close Browser Session"

# Summary
echo ""
echo "======================================"
log_success "Test suite completed!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Review test output above"
echo "2. Check test_screenshot.png"
echo "3. Verify all endpoints returned 2xx status codes"
echo ""
