#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ByteMind Content Automation — Complete Demo
# ─────────────────────────────────────────────────────────────────────────────
# This script demonstrates the full article publishing lifecycle:
#   1. Start the local stack (PostgreSQL + FastAPI)
#   2. Ingest a Markdown blog article
#   3. AI enrichment (SEO, LinkedIn summary, Medium bundle)
#   4. Publish to website + generate Medium syndication bundle
#   5. Show generated outputs
#
# Prerequisites:
#   - Docker & Docker Compose installed
#   - Python 3.12+ & pip installed
#   - .env file configured (copy .env.example → .env)
#
# Usage:
#   ./scripts/demo/run_demo.sh              # Full demo (starts stack)
#   ./scripts/demo/run_demo.sh --api-only   # Skip stack start (if already running)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEMO_ARTICLE="$SCRIPT_DIR/sample-article.md"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${BLUE}[DEMO]${NC} $1"; }
ok()   { echo -e "${GREEN}  ✓${NC} $1"; }
warn() { echo -e "${YELLOW}  ⚠${NC} $1"; }
fail() { echo -e "${RED}  ✗${NC} $1"; exit 1; }

# ─── Configuration ───────────────────────────────────────────────────────────

API_BASE="${API_BASE:-http://localhost:8000}"
API_KEY="${ACTIONS_API_KEY:-$(grep ACTIONS_API_KEY "$PROJECT_ROOT/.env" 2>/dev/null | cut -d= -f2-)}"

if [ -z "$API_KEY" ]; then
    fail "ACTIONS_API_KEY not found. Set it in .env or export it."
fi

# ─── Step 0: Start infrastructure ───────────────────────────────────────────

if [ "${1:-}" != "--api-only" ]; then
    log "Starting local stack (PostgreSQL + Redis + FastAPI)..."
    cd "$PROJECT_ROOT"
    docker compose -f docker-compose.dev.yml up -d --wait 2>/dev/null || {
        warn "docker-compose.dev.yml not available, trying docker-compose.yml"
        docker compose up -d --wait 2>/dev/null || warn "Docker stack not started (continue if API already running)"
    }
    sleep 3
fi

# ─── Step 1: Health check ────────────────────────────────────────────────────

log "Checking API health..."
HEALTH=$(curl -sf "$API_BASE/health" 2>/dev/null || echo "FAIL")
if echo "$HEALTH" | grep -q "ok\|healthy\|running"; then
    ok "API is running at $API_BASE"
else
    fail "API not reachable at $API_BASE. Start it first:\n       cd $PROJECT_ROOT && uvicorn app.main:app --reload"
fi

# ─── Step 2: Ingest & Enrich article ────────────────────────────────────────

log "Ingesting sample article: $(basename "$DEMO_ARTICLE")"
ARTICLE_CONTENT=$(cat "$DEMO_ARTICLE")

GENERATE_RESPONSE=$(curl -sf -X POST "$API_BASE/generate" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d "$(jq -n \
        --arg content "$ARTICLE_CONTENT" \
        --arg path "$DEMO_ARTICLE" \
        '{source_content: $content, source_path: $path}'
    )" 2>&1) || fail "POST /generate failed:\n$GENERATE_RESPONSE"

ARTICLE_ID=$(echo "$GENERATE_RESPONSE" | jq -r '.article_id')
IS_NEW=$(echo "$GENERATE_RESPONSE" | jq -r '.is_new')
STATUS=$(echo "$GENERATE_RESPONSE" | jq -r '.status')
GENERATED=$(echo "$GENERATE_RESPONSE" | jq -r '.generated_types | join(", ")')

ok "Article ingested & enriched"
echo -e "     ID:        $ARTICLE_ID"
echo -e "     New:       $IS_NEW"
echo -e "     Status:    $STATUS"
echo -e "     Generated: $GENERATED"

# ─── Step 3: Check article details ──────────────────────────────────────────

log "Fetching article details..."
ARTICLE_DETAIL=$(curl -sf "$API_BASE/articles" \
    -H "Authorization: Bearer $API_KEY" 2>/dev/null)

ARTICLE_COUNT=$(echo "$ARTICLE_DETAIL" | jq -r '.articles | length // 0' 2>/dev/null || echo "?")
ok "Total articles in database: $ARTICLE_COUNT"

# ─── Step 4: Publish article ─────────────────────────────────────────────────

log "Publishing article (website + Medium syndication bundle)..."
PUBLISH_RESPONSE=$(curl -sf -X POST "$API_BASE/publish" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d "$(jq -n \
        --arg id "$ARTICLE_ID" \
        '{article_id: $id, publisher: "website", publish_status: "draft"}'
    )" 2>&1) || {
    warn "Publishing skipped (article may need approval or already published)"
    PUBLISH_RESPONSE="{}"
}

PUB_STATUS=$(echo "$PUBLISH_RESPONSE" | jq -r '.status // "skipped"')
WEBSITE_URL=$(echo "$PUBLISH_RESPONSE" | jq -r '.website_url // "n/a"')
LINKEDIN_DIR=$(echo "$PUBLISH_RESPONSE" | jq -r '.linkedin_drafts_folder // "n/a"')
BUNDLE_PATH=$(echo "$PUBLISH_RESPONSE" | jq -r '.syndication_bundle_path // "n/a"')

if [ "$PUB_STATUS" != "skipped" ]; then
    ok "Published successfully"
    echo -e "     Status:           $PUB_STATUS"
    echo -e "     Website URL:      $WEBSITE_URL"
    echo -e "     LinkedIn drafts:  $LINKEDIN_DIR"
    echo -e "     Medium bundle:    $BUNDLE_PATH"
else
    warn "Publish returned no result (check approval workflow or article status)"
fi

# ─── Step 5: Show analytics ──────────────────────────────────────────────────

log "Fetching platform analytics..."
ANALYTICS=$(curl -sf "$API_BASE/analytics" \
    -H "Authorization: Bearer $API_KEY" 2>/dev/null || echo "{}")

TOTAL_ARTICLES=$(echo "$ANALYTICS" | jq -r '.total_articles // "?"')
TOTAL_TOKENS=$(echo "$ANALYTICS" | jq -r '.total_tokens_used // "?"')
TOTAL_PUBLISHED=$(echo "$ANALYTICS" | jq -r '.total_published // "?"')

ok "Platform stats"
echo -e "     Articles:    $TOTAL_ARTICLES"
echo -e "     Tokens used: $TOTAL_TOKENS"
echo -e "     Published:   $TOTAL_PUBLISHED"

# ─── Step 6: Show generated content samples ──────────────────────────────────

log "Fetching AI-generated content for this article..."
TOKEN_USAGE=$(curl -sf "$API_BASE/analytics/tokens" \
    -H "Authorization: Bearer $API_KEY" 2>/dev/null || echo "[]")

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  DEMO COMPLETE — Full Article Lifecycle Executed${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo "  What happened:"
echo "    1. Markdown article parsed (frontmatter + body)"
echo "    2. Article persisted to PostgreSQL"
echo "    3. AI engine (Gemini) generated:"
echo "       • SEO metadata (title, description, keywords)"
echo "       • LinkedIn post draft"
echo "       • Medium-formatted version with syndication bundle"
echo "       • Social media snippets"
echo "    4. Article published to website"
echo "    5. Medium syndication bundle saved to filesystem"
echo "    6. LinkedIn drafts generated"
echo "    7. Analytics updated"
echo ""
echo "  Next steps:"
echo "    • Review LinkedIn draft:  content/drafts/linkedin/"
echo "    • Import Medium bundle:   content/published/medium/"
echo "    • Check full API docs:    $API_BASE/docs"
echo ""
