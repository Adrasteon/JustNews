#!/usr/bin/env python3
"""Check installed protobuf version meets minimum requirement.

Usage:
  python scripts/check_protobuf_version.py

This tool examines the installed `protobuf` package version and exits with code 1 if it is older than the minimum required version.
"""
from __future__ import annotations
import sys
import pkg_resources

MIN_PROTOBUF = (4, 24, 0)

def parse_version(ver: str):
    parts = [int(x) for x in ver.split('.') if x.isdigit()]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])

def main():
    try:
        import google.protobuf as pb
        v = getattr(pb, '__version__', None) or getattr(pb, 'version', None)
        if not v:
            # fallback: check pkg_resources
            v = pkg_resources.get_distribution('protobuf').version
    except Exception as e:
        print('ERROR: protobuf not installed or could not be imported:', e)
        sys.exit(1)

    ver_tuple = parse_version(v)
    print('protobuf detected version:', v)
    if ver_tuple < MIN_PROTOBUF:
        print('ERROR: protobuf version older than recommended: >=%d.%d.%d' % MIN_PROTOBUF)
        print('Please update conda / pip environment to upgrade to protobuf >= 4.24.0')
        sys.exit(1)
    print('protobuf meets minimum version requirement.')

if __name__ == '__main__':
    main()
