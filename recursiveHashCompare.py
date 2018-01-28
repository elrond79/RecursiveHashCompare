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
import hashlib
from collections import namedtuple

from pathlib import Path

SUMMARY_EXTRA = ".summary"
SUMMARY_DEPTH_DEFAULT = 3


FileHashData = namedtuple('FileHashData', ['hash', 'size', 'file'])
DirHashData = namedtuple('DirHashData', ['hash', 'size', 'files', 'dirs'])
FilesHashData = namedtuple('FilesHashData', ['hash', 'size', 'files'])

class GenericHashData(object):
    def __init__(self, rootFolder)


class RecursiveHasher(object):
    def __init__(self, rootFolder, output_path):
        self.root_folder = Path(folder).resolve(strict=True)
        self.output_path = Path(output_path).resolve()
        self.make_output_hashes()

    def make_output_hashes(self):
        with open(self.output_path, 'w') as output_handle:
            self._recursive_hash(output_handle, self.root_folder, [])

    def _recursive_hash(self, output_handle, folder, folder_stack):
        subfiles = []
        subfolders = []
        for subpath in folder.iterdir():
            if subpath.is_symlink() or subpath.is_file():
                subfiles.append(subpath)
            else:
                subfolders.append(subpath)
        subfiles.sort()
        subfolders.sort()
        running_hash = hashlib.md5()
        running_size = 0
        all_file_datas = []
        for i, subfile in enumerate(subfiles):
            filehash = hashlib.md5()
            filesize = subfile.stat().st_size
            running_size += filesize
            filehash.update(subfile.read_bytes())
            filehash = fielhash.digest()
            subfile_data = FileHashData(filehash, filesize, str(subfile))
            all_file_datas.append(FileHashData)
            running_hash.update(subfile.name)
            running_hash.update(filehash)
        filesHashData = FilesHashData(running_hash.digest(), running_size,
            all_file_datas)

        all_subdir_datas = []
        for i, subfolder in enumerate(subfolders):
            subdirdata = self._recursive_hash(subfolder, output_handle)
            running_hash.update(subfolder.name)
            running_hash.update(subdirdata.hash)
            running_size += subdirdata.size
            all_subdir_datas.append(subdirdata)

        return DirHashData(running_hash.digest(), running_size,
            all_subdir_datas, filesHashData)

    

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