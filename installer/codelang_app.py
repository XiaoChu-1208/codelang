"""py2app entry point for codelang.app.

py2app builds a bundle around *this* script, tracing its imports. Keep it a
thin wrapper — all real logic lives in desktop.app.main(). The `desktop`
package is copied into the bundle via the `packages` option in setup_mac.py.
"""
import sys

from desktop.app import main

if __name__ == "__main__":
    sys.exit(main())
