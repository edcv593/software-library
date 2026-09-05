#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Software Library Manager v7 launcher.

The v7 UI/metadata changes are implemented in app.py directly. This file is
kept as a compatibility launcher so Docker and manual deployments do not need
an additional third-party dependency such as requests.
"""
import app

if __name__ == '__main__':
    import sys
    sys.argv[0] = 'app.py'
    app.main()
