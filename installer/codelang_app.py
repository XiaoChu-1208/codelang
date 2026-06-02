"""py2app entry point for codelang.app.

py2app builds a bundle around *this* script, tracing its imports. Keep it a
thin wrapper — all real logic lives in desktop.app.main(). The `desktop`
package is copied into the bundle via the `packages` option in setup_mac.py.
"""
import sys

# The bundle is code-signed; any .pyc Python writes at runtime adds an unsealed
# file and silently invalidates the signature — which makes macOS drop the
# app's Accessibility / Screen-Recording (TCC) grants, so global hotkeys and
# screenshot OCR stop working. All needed .pyc are precompiled, so never write
# new ones at runtime. Must be set before importing the desktop package.
sys.dont_write_bytecode = True

from desktop.app import main

if __name__ == "__main__":
    sys.exit(main())
