#!/usr/bin/env bash
# Run the UNO integration tests against a headless LibreOffice.
#
# Builds the extension, installs it into a throwaway LibreOffice profile,
# starts soffice headless with a UNO socket, and runs every scripts/uno_*.py
# test against it. Requires soffice/unopkg on PATH and a python3 that can
# "import uno" (Debian/Ubuntu: the python3-uno package).
#
#   ./scripts/run_uno_tests.sh
#   MLO_UNO_PORT=2100 ./scripts/run_uno_tests.sh
set -uo pipefail
cd "$(dirname "$0")/.."

PORT="${MLO_UNO_PORT:-2002}"
SOFFICE="${SOFFICE:-soffice}"
UNOPKG="${UNOPKG:-unopkg}"
PYTHON="${MLO_UNO_PYTHON:-python3}"

PROFILE_DIR="$(mktemp -d -t mlo-loprofile-XXXXXX)"
PROFILE_URL="file://$PROFILE_DIR"
SOFFICE_PID=""

cleanup() {
    if [ -n "$SOFFICE_PID" ] && kill -0 "$SOFFICE_PID" 2>/dev/null; then
        kill "$SOFFICE_PID" 2>/dev/null || true
        # Give it a moment to release the socket, then insist.
        for _ in $(seq 10); do
            kill -0 "$SOFFICE_PID" 2>/dev/null || break
            sleep 0.5
        done
        kill -9 "$SOFFICE_PID" 2>/dev/null || true
    fi
    rm -rf "$PROFILE_DIR"
}
trap cleanup EXIT

if ! "$PYTHON" -c "import uno" 2>/dev/null; then
    echo "ERROR: '$PYTHON' cannot import uno." >&2
    echo "Install python3-uno (Debian/Ubuntu) or set MLO_UNO_PYTHON to" >&2
    echo "LibreOffice's bundled python." >&2
    exit 1
fi

if [ "$(id -u)" = "0" ]; then
    # unopkg refuses to install a user extension when running as root,
    # which would silently leave the dispatch test with no extension.
    echo "ERROR: refusing to run as root — unopkg cannot install a user" >&2
    echo "extension as root. Run as an unprivileged user." >&2
    exit 1
fi

echo "==> Building extension"
./build.sh || { echo "ERROR: build failed" >&2; exit 1; }

echo "==> Installing extension into throwaway profile"
"$UNOPKG" add --force \
    "-env:UserInstallation=$PROFILE_URL" \
    dist/mendeley-libreoffice.oxt \
    || { echo "ERROR: unopkg could not install the extension" >&2; exit 1; }

echo "==> Starting headless soffice on port $PORT"
"$SOFFICE" --headless --norestore --nologo --nodefault \
    --nofirststartwizard --nolockcheck \
    "-env:UserInstallation=$PROFILE_URL" \
    --accept="socket,host=localhost,port=$PORT;urp;" &
SOFFICE_PID=$!

# Wait for the UNO socket to accept connections.
for _ in $(seq 60); do
    if "$PYTHON" - "$PORT" <<'EOF' 2>/dev/null
import socket, sys
s = socket.create_connection(("localhost", int(sys.argv[1])), timeout=1)
s.close()
EOF
    then
        break
    fi
    if ! kill -0 "$SOFFICE_PID" 2>/dev/null; then
        echo "ERROR: soffice exited before opening port $PORT" >&2
        exit 1
    fi
    sleep 1
done

echo "==> Running UNO tests"
failed=""
for test in uno_smoke uno_docx_roundtrip uno_word_import_test \
            uno_dispatch_check; do
    echo "--- $test"
    if "$PYTHON" "scripts/$test.py" "$PORT"; then
        :
    else
        failed="$failed $test"
    fi
done

if [ -n "$failed" ]; then
    echo "UNO TESTS FAILED:$failed" >&2
    exit 1
fi
echo "UNO TESTS OK"
