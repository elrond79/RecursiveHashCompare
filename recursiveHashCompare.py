#!/usr/bin/env python3

'''Generate a file all the files + folders in a target folder, with their hashes

Designed to be run locally on two separate computers, then the copy the
resulting file over to one, where it may be diffed.  Much faster then comparing
over a network.
'''


#rootpath = r"C:\Users\paulm\.thumbnails\normal"
#rhc_globals = runpy.run_path(r"C:\Users\paulm\Desktop\RecursiveHashCompare\recursiveHashCompare.py"); globals().update(rhc_globals); data = DirHashData(rootpath); print(data)


import os
import sys
import argparse
import pathlib
import hashlib
import binascii

from pathlib import Path

SUMMARY_EXTRA = ".summary"
SUMMARY_DEPTH_DEFAULT = 3


class BaseHashData(object):
    INDENT = ' ' * 2

    def __str__(self):
        return '\n'.join(self._strlines(0))

    def hexhash(self):
        return binascii.hexlify(self.hash).decode('ascii')


class FileHashData(BaseHashData):
    def __init__(self, filepath):
        if not isinstance(filepath, pathlib.Path):
            filepath = pathlib.Path(filepath)
        self.path = str(filepath)
        self.size = filepath.stat().st_size
        filehash = hashlib.md5()
        filehash.update(filepath.read_bytes())
        self.hash = filehash.digest()         

    def _strlines(self, indent_level):
        return ['{}{} - {:,} - {}'.format(self.INDENT * indent_level,
            os.path.basename(self.path), self.size, self.hexhash())]
    

class FilesHashData(BaseHashData):
    def __init__(self, files):
        self.files = []
        for f in files:
            if not isinstance(f, FileHashData):
                f = FileHashData(f)
            self.files.append(f)

        running_hash = hashlib.md5()
        self.size = 0
        for filehash in self.files:
            self.size += filehash.size
            running_hash.update(os.path.basename(filehash.path).encode('utf8'))
            running_hash.update(filehash.hash)
        self.hash = running_hash.digest()

    def _strlines(self, indent_level):
        lines = ['{}<files> - {:,} - {}'.format(self.INDENT * indent_level,
            self.size, self.hexhash())]
        for filedata in self.files:
            lines.extend(filedata._strlines(indent_level + 1))
        return lines


class DirHashData(BaseHashData):
    def __init__(self, folderpath):
        if not isinstance(folderpath, pathlib.Path):
            folderpath = pathlib.Path(folderpath)
        self.path = str(folderpath)
        subfiles = []
        subfolders = []
        for subpath in folderpath.iterdir():
            if subpath.is_symlink() or subpath.is_file():
                subfiles.append(subpath)
            else:
                subfolders.append(subpath)
        subfiles.sort()
        subfolders.sort()

        self.size = 0
        running_hash = hashlib.md5()
        
        self.files = FilesHashData(subfiles)

        self.size += self.files.size
        running_hash.update(self.files.hash)

        self.dirs = []
        for subfolder in subfolders:
            subdirdata = type(self)(subfolder)
            self.dirs.append(subdirdata)
            self.size += subdirdata.size
            running_hash.update(subfolder.name.encode('utf8'))
            running_hash.update(subdirdata.hash)
        self.hash = running_hash.digest()

    def _strlines(self, indent_level):
        lines = ['{}{} - {:,} - {}'.format(self.INDENT * indent_level,
            os.path.basename(self.path), self.size, self.hexhash())]
        for dirdata in self.dirs:
            lines.extend(dirdata._strlines(indent_level + 1))
        lines.extend(self.files._strlines(indent_level + 1))
        return lines


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