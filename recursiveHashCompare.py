#!/usr/bin/env python3

'''Generate a file all the files + folders in a target folder, with their hashes

Designed to be run locally on two separate computers, then the copy the
resulting file over to one, where it may be diffed.  Much faster then comparing
over a network.
'''

import os
import sys
import argparse
import pathlib

from pathlib import Path

SUMMARY_EXTRA = ".summary"
SUMMARY_DEPTH_DEFAULT = 3

class RecursiveHasher(object):
    def __init__(self, rootFolder, output_path):


def output_hashes(folder, output_path):
    folder = Path(folder).resolve(strict=True)
    output_path = Path(output_path).resolve()

    with open(output_path, 'w') as output_handle:
        recursive_hash(folder, output_handle, [])

def recursive_hash(folder, output_handle, parent_folders):
    hashes = []
    subfiles = []
    subfolders = []
    for subpath in folder.iterdir():
        if subpath.is_symlink() or subpath.is_file():
            subfiles.append(subpath)
        else:
            subfolders.append(subpath)
    subfiles.sort()
    subfolders.sort()
    # do depth first - subfolders first
    for i, subfolder in enumerate(subfolders):
        do
        recursive_hash(subfolder, output_handle, summary_handle, summary_depth,
            parent_folders + [subfolder, i, len(subfolders)])
    for i, f in enumerate(subfiles):


def doUpdate(folderProgress, fileNum, totalFiles):

    

def get_parser():
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('dir',
        help='Directory to generate hash for - default to current directory',
        default=".")
    parser.add_argument('output',
        help='Path to file to generate output hash information in',
        default="md5_hashes.txt")
    return parser

def main(args=sys.argv[1:]):
    parser = get_parser()
    args = parser.parse_args(args)
    output_hashes(args.dir, args.output, summary_path=args.summary,
        summary_depth=args.summary_depth)


if __name__ == '__main__':
    main()