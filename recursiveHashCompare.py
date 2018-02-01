#!/usr/bin/env python3

'''Generate recursive size + hash info recursively for a target folder

Designed to be run locally on two separate computers, then the copy the
resulting file(s) over to one, where it may be diffed.  Much faster then
streaming entire file contents over a network for comparison.
'''


#rootpath = r"C:\Users\paulm\.thumbnails\normal"
#rootpath = r"C:\Users\paulm\Desktop"
#rhc_globals = runpy.run_path(r"C:\Users\paulm\Desktop\RecursiveHashCompare\recursiveHashCompare.py"); globals().update(rhc_globals); updater = Updater(); data = DirHashData(rootpath, updater=updater); print(data)
#C:\Apps\DevTools\Python36\python.exe recursiveHashCompare.py "C:\Users\paulm\Desktop\Adobe Acrobat XI Pro 11.0.3 Multilanguage [ChingLiu]" "C:\Users\paulm\Desktop\Acrobot_hash.pickle"
#C:\Apps\DevTools\Python36\python.exe recursiveHashCompare.py "D:" "C:\Users\paulm\Desktop\d_drive.pickle" -i 60

import os
import sys
import argparse
import pathlib
import hashlib
import binascii
import datetime
import pickle
import re
import traceback

from pathlib import Path


SUMMARY_EXTRA = ".summary"
SUMMARY_DEPTH_DEFAULT = 3
DEFAULT_INTERVAL = 10
DEFAULT_BUFFER_SIZE = 4096
LONGPATH_PREFIX = '\\\\?\\'
ERROR_HASH = binascii.a2b_hex('bad00000000000000000000000000000')


class Updater(object):
    def __init__(self, interval=datetime.timedelta(seconds=DEFAULT_INTERVAL)):
        self.start = datetime.datetime.now()
        self.last = self.start
        if not isinstance(interval, datetime.timedelta):
            interval = datetime.timedelta(seconds=interval)
        self.interval = interval

    def update(self, current_path, dir_progress):
        now = datetime.datetime.now()
        if (now - self.last) >= self.interval:            
            elapsed = now - self.start
            progress_strs = []
            for dir_i, num_dirs in dir_progress:
                progress_strs.append("{}/{}".format(dir_i, num_dirs))
            progress_str = ' - '.join(progress_strs)
            print(current_path)
            print(f"{elapsed} - {progress_str}")
            self.last = now


class BaseHashData(object):
    INDENT = ' ' * 2

    def __str__(self):
        return '\n'.join(self.strlines(0))

    def hexhash(self):
        return binascii.hexlify(self.hash).decode('ascii')

    @classmethod
    def get_extended_path(cls, path):
        if not isinstance(path, pathlib.Path):
            path = pathlib.Path(path)
        if not isinstance(path, pathlib.PureWindowsPath):
            return path
        if len(str(path)) < 256 or str(path).startswith(LONGPATH_PREFIX):
            return path
        return type(path)(LONGPATH_PREFIX + str(path))

    def get_short_path(cls, path):
        if not isinstance(path, pathlib.Path):
            path = pathlib.Path(path)
        if not isinstance(path, pathlib.PureWindowsPath):
            return path
        if str(path).startswith(LONGPATH_PREFIX):
            return pathlib.Path(str(path)[len(LONGPATH_PREFIX):])
        return path

    @property
    def path_str(self):
        result = str(self._path)
        if result.startswith(LONGPATH_PREFIX):
            result = result[len(LONGPATH_PREFIX):]
        return result

    @property
    def path_obj(self):
        return self._path

    # this is just here to block assigning to self.path
    @property
    def path(self):
        raise Exception

    def set_path(self, value):
        self._path = self.get_extended_path(value)


class FileHashData(BaseHashData):
    def __init__(self, filepath, updater=None, progress=None, root_dir=None):
        self.root_dir = root_dir
        self.error = None
        if updater:
            if not progress:
                progress = []
            updater.update(filepath, progress)

        self.set_path(filepath)
        stat = self.path_obj.stat()
        self.size = stat.st_size
        filehash = hashlib.md5()

        if hasattr(stat, 'st_blksize') and stat.st_blksize:
            buffer_size = stat.st_blksize
        else:
            buffer_size = DEFAULT_BUFFER_SIZE
        try:
            with self.path_obj.open('rb') as f:
                while True:
                    data = f.read(buffer_size)
                    if not data:
                        break
                    filehash.update(data)
        except Exception as e:
            self.error = e
            self.hash = ERROR_HASH
            print("Error reading {self.path_str}:")
            traceback.print_exc()
        else:
            self.hash = filehash.digest()

    def strlines(self, indent_level):
        return ['{}{} - {:,} - {}'.format(self.INDENT * indent_level,
            os.path.basename(self.path_str), self.size, self.hexhash())]
    

class FilesHashData(BaseHashData):
    def __init__(self, files, updater=None, progress=None, root_dir=None):
        self.files = []

        running_hash = hashlib.md5()
        self.size = 0
        for i, filehash in enumerate(files):
            if updater:
                new_progress = progress + [(i + 1, len(files))]
            else:
                new_progress = None            
            if not isinstance(filehash, FileHashData):
                filehash = FileHashData(filehash, updater=updater,
                    progress=new_progress, root_dir=root_dir)
            self.files.append(filehash)
            self.size += filehash.size
            running_hash.update(os.path.basename(filehash.path_str).encode('utf8'))
            running_hash.update(filehash.hash)
        self.hash = running_hash.digest()

    def strlines(self, indent_level):
        yield '{}<files> - {:,} - {}'.format(self.INDENT * indent_level,
            self.size, self.hexhash())
        for filedata in self.files:
            for line in filedata.strlines(indent_level + 1):
                yield line


class DirHashData(BaseHashData):
    def __init__(self, folderpath, updater=None, progress=None, exclude=(),
                 root_dir=None):
        if root_dir is None:
            root_dir = self
        self.root_dir = root_dir
        self.exclude = exclude
        if updater:
            if not progress:
                progress = []
            updater.update(folderpath, progress)

        self.set_path(folderpath)
        subfiles = []
        subfolders = []
        for subpath in self.path_obj.iterdir():
            subpath = self.get_extended_path(subpath)
            if self.is_excluded(subpath):
                continue
            if subpath.is_symlink() or subpath.is_file():
                subfiles.append(subpath)
            else:
                subfolders.append(subpath)
        subfiles.sort()
        subfolders.sort()

        self.size = 0
        running_hash = hashlib.md5()
        
        self.files = FilesHashData(subfiles, updater=updater, progress=progress,
                                   root_dir=root_dir)

        self.size += self.files.size
        running_hash.update(self.files.hash)

        self.dirs = []
        for i, subfolder in enumerate(subfolders):
            if updater:
                new_progress = progress + [(i + 1, len(subfolders))]
            else:
                new_progress = None
            subdirdata = type(self)(subfolder, updater=updater,
                progress=new_progress, root_dir=root_dir)
            self.dirs.append(subdirdata)
            self.size += subdirdata.size
            running_hash.update(subfolder.name.encode('utf8'))
            running_hash.update(subdirdata.hash)
        self.hash = running_hash.digest()

    def is_excluded(self, path):
        if not self.root_dir.exclude:
            return False
        root_path = self.get_short_path(self.root_dir.path_obj)
        path = self.get_short_path(path)
        rel_path = str(path.relative_to(root_path))
        for exclusion_re in self.root_dir.exclude:
            if exclusion_re.match(rel_path):
                return True
        return False

    def strlines(self, indent_level):
        if self.root_dir is self:
            pathname = self.path_str
        else:
            pathname = os.path.basename(self.path_str)
        yield '{}{} - {:,} - {}'.format(self.INDENT * indent_level,
            pathname, self.size, self.hexhash())
        for dirdata in self.dirs:
            for line in dirdata.strlines(indent_level + 1):
                yield line
        for line in self.files.strlines(indent_level + 1):
            yield line


def write_hashes(folder, output_path, interval=DEFAULT_INTERVAL, exclude=()):
    if interval > 0:
        updater = Updater(interval)
    else:
        updater = None
    if isinstance(exclude, str):
        exclude = [exclude]
    exclude = [x if isinstance(x, re._pattern_type)
               else re.compile(x) for x in exclude]

    def ensure_slash_after_drive(input_path):
        '''Fix paths like E:folder to E:\folder

        Note that even Path.absolute won't work here'''
        if not isinstance(input_path, pathlib.Path):
            input_path = pathlib.Path(input_path)
        if not input_path.is_absolute() and input_path.drive:
            parts = list(input_path.parts)
            assert parts[0] == input_path.drive
            if len(parts) == 1:
                parts.append(os.path.sep)
            else:
                parts[1] = os.path.sep + parts[1]
            return type(input_path)(*parts)
        return input_path
    folder = ensure_slash_after_drive(folder)
    output_path = ensure_slash_after_drive(output_path)

    output_base, output_ext = os.path.splitext(str(output_path))
    if output_ext == '.txt':
        output_txt = output_path
        output_pickle = output_base + '.pickle'
    else:
        output_pickle = output_path
        output_txt = output_base + '.txt'

    # we do a test open of both output paths to make sure they're writable
    # before doing whole crawl!
    with open(output_pickle, 'ab') as f:
        pass

    with open(output_txt, 'a') as f:
        pass

    dirdata = DirHashData(folder, updater=updater, exclude=exclude)

    with open(output_pickle, 'wb') as f:
        pickle.dump(dirdata, f, protocol=pickle.HIGHEST_PROTOCOL)

    encoding = 'utf8'
    with open(output_txt, 'w', encoding=encoding) as f:
        f.write(f'# -*- coding: {encoding} -*-\n\n')
        for line in dirdata.strlines(0):
            f.write(line)
            f.write('\n')

def get_parser():
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('dir',
        help='Directory to generate hash for - default to current directory',
        default=".")
    parser.add_argument('output',
        help='Path to file to generate output hash information in',
        default="md5_hashes.pickle")
    parser.add_argument('-i', '--interval', type=int, default=DEFAULT_INTERVAL,
        help="How often to print out progress updates, in seconds; set to 0"
            " in order to disable updates")
    parser.add_argument('-e', '--exclude', action='append', default=[],
        help="Regular expression for paths to exclude (relative to base DIR);"
             " may be given multiple times")
    return parser


def main(args=sys.argv[1:]):
    parser = get_parser()
    args = parser.parse_args(args)
    write_hashes(args.dir, args.output, interval=args.interval,
                 exclude=args.exclude)


if __name__ == '__main__':
    main()