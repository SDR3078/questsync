"""Runtime settings for QuestSync, including the build-time-gated demo switch."""
import logging
import os

# Demo mode (accept ANY credentials + serve fixtures) is enabled ONLY when the
# runtime flag is set AND the image was built with the demo marker (the `dev`
# Docker target creates it). A single prod env var therefore cannot turn it on.
_MARKER = "/etc/questsync/demo-allowed"
DEMO = os.environ.get("QUESTSYNC_DEMO") == "1" and os.path.exists(_MARKER)

_log = logging.getLogger("radicale")
if DEMO:
    _log.warning("QUESTSYNC DEMO MODE: accepting ANY credentials and serving "
                 "fixture data — never use this in production.")
elif os.environ.get("QUESTSYNC_DEMO") == "1":
    _log.warning("QUESTSYNC_DEMO=1 ignored: this image lacks the demo marker "
                 "(%s); demo is a build-time-gated dev feature." % _MARKER)
