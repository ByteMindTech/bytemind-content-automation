"""GraphQL endpoint for Medium story management.

Provides a full GraphQL API for managing Medium stories:
  - Query: listStories, story, me
  - Mutation: createStory, updateStory, deleteStory, publishStory, setTags

Authentication: Bearer token (JWT or API key) required via Authorization header.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import strawberry
from fastapi import Depends, Request
from strawberry.fastapi import GraphQLRouter
from strawberry.types import Info

from app.config import get_settings
from app.medium.graphql_publisher import COOKIES_PATH, GRAPHQL_URL, MediumGraphQLPublisher
from app.security.auth import require_api_key
from app.utils.logging import get_logger

if TYPE_CHECKING:
    pass

import requests

logger = get_logger(__name__)
_settings = get_settings()


# ── GraphQL Types ─────────────────────────────────────────────────────────────


@strawberry.type
class MediumUser:
    id: str
    username: str
    name: str
    bio: str
    image_url: str
    url: str


@strawberry.type
class StoryTag:
    slug: str
    name: str


@strawberry.type
class Story:
    id: str
    title: str
    url: str
    edit_url: str
    status: str
    created_at: str
    updated_at: str
    word_count: int
    tags: list[StoryTag]
    canonical_url: str


@strawberry.type
class StoryPreview:
    id: str
    title: str
    url: str
    status: str
    created_at: str


@strawberry.type
class PublishResult:
    post_id: str
    url: str
    edit_url: str
    status: str
    paragraphs_count: int
    dry_run: bool


@strawberry.type
class DeleteResult:
    success: bool
    post_id: str


@strawberry.type
class TagsResult:
    post_id: str
    tags: list[str]


# ── Medium API Client (internal) ─────────────────────────────────────────────


def _get_medium_session() -> tuple[dict[str, str], dict[str, str]]:
    """Load cookies and establish authenticated session with Medium."""
    if not COOKIES_PATH.exists():
        raise ValueError(
            "Medium cookies not configured. Save uid and sid to content/.medium-cookies.json"
        )
    data = json.loads(COOKIES_PATH.read_text())
    cookies = {c["name"]: c["value"] for c in data} if isinstance(data, list) else data

    # Fetch XSRF token with browser-like headers to avoid Cloudflare blocks
    session_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    r = requests.get("https://medium.com/", cookies=cookies, headers=session_headers, timeout=15)
    if r.status_code == 403:
        raise ValueError(
            "Medium blocked by Cloudflare (403). This typically happens from data center IPs. "
            "Use this endpoint from a non-blocked network or configure a proxy."
        )
    xsrf = r.cookies.get("xsrf", "")
    cookies["xsrf"] = xsrf
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-XSRF-Token": xsrf,
        "X-Obvious-CK": "true",
        "User-Agent": session_headers["User-Agent"],
    }
    return cookies, headers


def _medium_graphql(query: str, variables: dict, cookies: dict, headers: dict) -> dict:
    """Execute a GraphQL query against Medium's API."""
    r = requests.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables},
        cookies=cookies,
        headers=headers,
        timeout=20,
    )
    text = r.text
    if text.startswith("])}"):
        text = text[text.index("{"):]
    return json.loads(text) if text else {}


def _medium_rest(path: str, cookies: dict) -> dict:
    """Execute a REST GET against Medium's API."""
    # Medium's REST endpoints use different patterns:
    # - /me?format=json for user info
    # - /_/api/posts/{id} for post data
    if path == "/me":
        url = "https://medium.com/me?format=json"
    else:
        url = f"https://medium.com/_/api{path}"

    r = requests.get(
        url,
        cookies=cookies,
        headers={
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        },
        timeout=15,
    )
    if r.status_code == 403:
        raise ValueError("Medium blocked by Cloudflare (403)")
    text = r.text
    if text.startswith("])}"):
        text = text[text.index("{"):]
    try:
        return json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        return {}


# ── Queries ───────────────────────────────────────────────────────────────────


@strawberry.type
class Query:
    @strawberry.field(description="Get current Medium user profile")
    def me(self, info: Info) -> MediumUser:
        cookies, headers = _get_medium_session()
        data = _medium_rest("/me", cookies)
        user = data.get("payload", {}).get("user", {})
        return MediumUser(
            id=user.get("userId", ""),
            username=user.get("username", ""),
            name=user.get("name", ""),
            bio=user.get("bio", ""),
            image_url=user.get("imageUrl", ""),
            url=f"https://medium.com/@{user.get('username', '')}",
        )

    @strawberry.field(description="Get a story by ID")
    def story(self, info: Info, story_id: str) -> Story:
        cookies, headers = _get_medium_session()
        data = _medium_rest(f"/posts/{story_id}", cookies)
        post = data.get("payload", {}).get("value", {})
        if not post:
            raise ValueError(f"Story '{story_id}' not found")
        return _post_to_story(post)

    @strawberry.field(description="List user's stories (drafts and published)")
    def list_stories(self, info: Info, limit: int = 20) -> list[StoryPreview]:
        cookies, headers = _get_medium_session()

        # Use viewer query with postsConnection (requires after cursor)
        query = """
        query ListPosts($first: Int!, $after: String!) {
          viewer {
            postsConnection(first: $first, after: $after) {
              edges {
                node {
                  id title createdAt mediumUrl
                  isPublished
                }
              }
            }
          }
        }
        """
        data = _medium_graphql(
            query, {"first": min(limit, 50), "after": ""}, cookies, headers
        )

        viewer = data.get("data", {}).get("viewer", {})
        edges = viewer.get("postsConnection", {}).get("edges", [])

        stories = []
        for edge in edges:
            node = edge.get("node", {})
            stories.append(
                StoryPreview(
                    id=node.get("id", ""),
                    title=node.get("title", "Untitled"),
                    url=node.get("mediumUrl", ""),
                    status="published" if node.get("isPublished") else "draft",
                    created_at=str(node.get("createdAt", "")),
                )
            )

        return stories


# ── Mutations ─────────────────────────────────────────────────────────────────


@strawberry.input
class CreateStoryInput:
    title: str
    markdown_body: str
    tags: list[str] | None = None
    canonical_url: str | None = None
    status: str = "draft"


@strawberry.input
class UpdateStoryInput:
    story_id: str
    title: str | None = None
    markdown_body: str | None = None
    tags: list[str] | None = None


@strawberry.type
class Mutation:
    @strawberry.mutation(description="Create and publish a new story from markdown content")
    def create_story(self, info: Info, input: CreateStoryInput) -> PublishResult:
        publisher = MediumGraphQLPublisher()
        result = publisher.publish(
            title=input.title,
            markdown_body=input.markdown_body,
            tags=input.tags,
            canonical_url=input.canonical_url,
            publish_status=input.status,
        )
        logger.info("graphql_story_created", post_id=result["post_id"])
        return PublishResult(
            post_id=result["post_id"],
            url=result["url"],
            edit_url=result.get("edit_url", ""),
            status=result["status"],
            paragraphs_count=result.get("paragraphs_count", 0),
            dry_run=result.get("dry_run", False),
        )

    @strawberry.mutation(description="Update an existing story's content and/or tags")
    def update_story(self, info: Info, input: UpdateStoryInput) -> PublishResult:
        cookies, headers = _get_medium_session()

        paragraphs_count = 0

        # If markdown_body provided, push new content (replaces existing)
        if input.markdown_body:
            from app.medium.graphql_publisher import markdown_to_deltas

            title = input.title or "Untitled"
            deltas = markdown_to_deltas(title, input.markdown_body)

            # Get current revision
            query = "query { post(id: \"%s\") { latestRev } }" % input.story_id
            rev_data = _medium_graphql(query, {}, cookies, headers)
            latest_rev = rev_data.get("data", {}).get("post", {}).get("latestRev", -1)

            # Push deltas
            update_q = (
                "mutation UpdatePost($responseId: ID!, $latestRev: Int!, $deltas: [Delta!]!) "
                "{ updatePostResponse(responseId: $responseId, latestRev: $latestRev, "
                "deltas: $deltas) { __typename } }"
            )
            import time

            batch_size = 50
            rev = latest_rev
            for start in range(0, len(deltas), batch_size):
                batch = deltas[start : start + batch_size]
                _medium_graphql(
                    update_q,
                    {"responseId": input.story_id, "latestRev": rev, "deltas": batch},
                    cookies,
                    headers,
                )
                rev += len(batch)
                if start + batch_size < len(deltas):
                    time.sleep(1)

            paragraphs_count = len(deltas)

        # If tags provided, update them
        if input.tags is not None:
            tag_q = (
                "mutation SetTags($targetPostId: ID!, $tagNames: [String!]!) "
                "{ setPostTags(targetPostId: $targetPostId, tagNames: $tagNames) "
                "{ __typename } }"
            )
            _medium_graphql(
                tag_q,
                {"targetPostId": input.story_id, "tagNames": input.tags[:5]},
                cookies,
                headers,
            )

        logger.info("graphql_story_updated", post_id=input.story_id)
        return PublishResult(
            post_id=input.story_id,
            url=f"https://medium.com/@melhosni/{input.story_id}",
            edit_url=f"https://medium.com/p/{input.story_id}/edit",
            status="updated",
            paragraphs_count=paragraphs_count,
            dry_run=False,
        )

    @strawberry.mutation(description="Delete a story permanently")
    def delete_story(self, info: Info, story_id: str) -> DeleteResult:
        cookies, headers = _get_medium_session()
        query = (
            "mutation DeletePost($targetPostId: ID!) "
            "{ deletePost(targetPostId: $targetPostId) }"
        )
        data = _medium_graphql(query, {"targetPostId": story_id}, cookies, headers)
        success = data.get("data", {}).get("deletePost", False)
        logger.info("graphql_story_deleted", post_id=story_id, success=success)
        return DeleteResult(success=bool(success), post_id=story_id)

    @strawberry.mutation(description="Publish a draft story to public")
    def publish_story(self, info: Info, story_id: str) -> PublishResult:
        cookies, headers = _get_medium_session()
        query = (
            "mutation PublishPost($postId: ID!) "
            "{ publishPost(postId: $postId) { __typename } }"
        )
        _medium_graphql(query, {"postId": story_id}, cookies, headers)
        logger.info("graphql_story_published", post_id=story_id)
        return PublishResult(
            post_id=story_id,
            url=f"https://medium.com/@melhosni/{story_id}",
            edit_url=f"https://medium.com/p/{story_id}/edit",
            status="public",
            paragraphs_count=0,
            dry_run=False,
        )

    @strawberry.mutation(description="Set or update tags on a story (max 5)")
    def set_tags(self, info: Info, story_id: str, tags: list[str]) -> TagsResult:
        cookies, headers = _get_medium_session()
        query = (
            "mutation SetTags($targetPostId: ID!, $tagNames: [String!]!) "
            "{ setPostTags(targetPostId: $targetPostId, tagNames: $tagNames) "
            "{ __typename } }"
        )
        _medium_graphql(
            query,
            {"targetPostId": story_id, "tagNames": tags[:5]},
            cookies,
            headers,
        )
        logger.info("graphql_tags_updated", post_id=story_id, tags=tags[:5])
        return TagsResult(post_id=story_id, tags=tags[:5])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _post_to_story(post: dict) -> Story:
    """Convert Medium's internal post format to our Story type."""
    virtuals = post.get("virtuals", {})
    tags_raw = virtuals.get("tags", [])
    tags = [
        StoryTag(slug=t.get("slug", ""), name=t.get("displayTitle", t.get("name", "")))
        for t in tags_raw
    ]

    created = post.get("createdAt", 0)
    updated = post.get("updatedAt", 0)

    # Determine status
    if post.get("visibility") == "PUBLIC":
        status = "published"
    elif post.get("latestPublishedVersion"):
        status = "published"
    else:
        status = "draft"

    return Story(
        id=post.get("id", ""),
        title=post.get("title", "Untitled"),
        url=post.get("mediumUrl", f"https://medium.com/@melhosni/{post.get('id', '')}"),
        edit_url=f"https://medium.com/p/{post.get('id', '')}/edit",
        status=status,
        created_at=str(created),
        updated_at=str(updated),
        word_count=virtuals.get("wordCount", 0),
        tags=tags,
        canonical_url=post.get("canonicalUrl", ""),
    )


# ── Auth context dependency ───────────────────────────────────────────────────


async def get_context(
    request: Request,
    subject: str = Depends(require_api_key),
) -> dict:
    """Inject authenticated subject into GraphQL context."""
    return {"request": request, "subject": subject}


# ── Schema & Router ───────────────────────────────────────────────────────────

schema = strawberry.Schema(query=Query, mutation=Mutation)

graphql_app = GraphQLRouter(
    schema,
    context_getter=get_context,
    path="/",
)
