#!/bin/sh
# Publish a release from this machine, without CI: the image goes to Docker Hub
# first, then the git tag and the GitHub release, so a release never exists
# without its image.
#
#   make release VERSION=0.2.0 [NOTES=notes.md]   # DRY_RUN=1 prints the steps only
#
# Tags: every release moves :staging; a stable one also moves :latest and :X.Y.
# PULSE_RELEASE_HOOK, if set, runs once per channel the release moved (staging,
# then production) with PULSE_RELEASE_CHANNEL and PULSE_RELEASE_VERSION set, to
# redeploy right away instead of waiting for the platform to notice, e.g.
#   export PULSE_RELEASE_HOOK='railway redeploy --service "pulse-$PULSE_RELEASE_CHANNEL" --yes'
#
# Needs: docker (signed in to Docker Hub), gh (signed in), and the version bump
# merged to main.
set -eu

version=${1:-}
notes=${2:-}
image=${PULSE_RELEASE_IMAGE:-neecat/pulse}
builder=pulse-release
tag="v$version"

fail() { echo "✗ $*" >&2; exit 1; }
run() {
  if [ "${DRY_RUN:-}" = 1 ]; then echo "  would run: $*"; else "$@"; fi
}

echo "$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9a-z.]+)?$' ||
  fail "Give a version: make release VERSION=x.y.z"
[ -z "$notes" ] || [ -f "$notes" ] || fail "Notes file not found: $notes"

# 1. Release exactly what's merged on main.
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || fail "Check out main first."
git fetch -q origin main --tags
[ -z "$(git status --porcelain)" ] || fail "Commit or stash your changes first."
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] ||
  fail "main isn't the same as origin/main. Run git pull."

if ! grep -q "^version = \"$version\"" backend/pyproject.toml ||
  ! grep -q "__version__ = \"$version\"" backend/src/pulse/__init__.py ||
  ! grep -q "\"version\": \"$version\"" frontend/package.json; then
  fail "Bump the version to $version (pyproject.toml, __init__.py, package.json) and merge it first."
fi

if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
  [ "$(git rev-parse "$tag^{commit}")" = "$(git rev-parse HEAD)" ] ||
    fail "$tag already exists on another commit."
fi
if gh release view "$tag" >/dev/null 2>&1; then
  fail "The GitHub release $tag already exists."
fi

# 2. Same checks as CI.
echo "→ Checking"
run make check

# 3. The image, for amd64 and arm64. Pre-releases (x.y.z-rc.1) never become latest.
set -- -t "$image:$version" -t "$image:staging"
case $version in
  *-*) prerelease=1; channels=staging ;;
  *) prerelease=0; channels="staging production"
    set -- "$@" -t "$image:${version%.*}" -t "$image:latest" ;;
esac
echo "→ Building and pushing $image:$version"
docker buildx inspect "$builder" >/dev/null 2>&1 ||
  run docker buildx create --name "$builder" --driver docker-container
run docker buildx build --builder "$builder" --platform linux/amd64,linux/arm64 \
  --label "org.opencontainers.image.version=$version" \
  --label "org.opencontainers.image.revision=$(git rev-parse HEAD)" \
  --label "org.opencontainers.image.created=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "$@" --push .

# 4. Only now the tag and the GitHub release.
echo "→ Tagging and creating the GitHub release"
git rev-parse -q --verify "refs/tags/$tag" >/dev/null ||
  run git tag -a "$tag" -m "Pulse $version"
run git push origin "$tag"
set -- --title "Pulse $version" --verify-tag
if [ -n "$notes" ]; then set -- "$@" --notes-file "$notes"; else set -- "$@" --generate-notes; fi
if [ "$prerelease" = 1 ]; then set -- "$@" --prerelease --latest=false; else set -- "$@" --latest; fi
run gh release create "$tag" "$@"

# 5. Optionally tell the deployments that follow these tags. The release is already
#    out, so a failing hook only warns.
if [ -n "${PULSE_RELEASE_HOOK:-}" ]; then
  export PULSE_RELEASE_VERSION="$version"
  for PULSE_RELEASE_CHANNEL in $channels; do
    export PULSE_RELEASE_CHANNEL
    echo "→ Redeploying $PULSE_RELEASE_CHANNEL"
    run sh -c "$PULSE_RELEASE_HOOK" || echo "! The $PULSE_RELEASE_CHANNEL redeploy failed; redeploy it by hand." >&2
  done
fi

echo "✓ Released $version: docker pull $image:$version"
