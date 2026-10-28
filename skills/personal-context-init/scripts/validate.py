#!/usr/bin/env python3
"""Read-only structural validation; does not validate personal facts."""
import argparse
import json
import sys
from manage import root_path, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target')
    args = parser.parse_args()
    try:
        result = validate(root_path(args.target))
    except (ValueError, OSError) as exc:
        result = {'ok': False, 'errors': [str(exc)], 'warnings': []}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
