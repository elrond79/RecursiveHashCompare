#!/usr/bin/env python3

'''Generate recursive size + hash info recursively for a target folder

Designed to be run locally on two separate computers, then the copy the
resulting file(s) over to one, where it may be diffed.  Much faster then
streaming entire file contents over a network for comparison.
'''

#rootpath = r"C:\Users\paulm\.thumbnails\normal"
#rootpath = r"C:\Users\paulm\Desktop"
#rhc_globals = runpy.run_path(r"C:\Users\paulm\Desktop\RecursiveHashCompare\recursiveHashCompare.py"); globals().update(rhc_globals); updater = Updater(); data = DirHashData(rootpath, updater=updater); print(data)

# Desktop d
#C:\Apps\DevTools\Python36\python.exe -u "C:\Users\paulm\Desktop\RecursiveHashCompare\recursiveHashCompare.py" --add-date "D:" "C:\Users\paulm\Desktop\d_drive" -i 60 --exclude "System Volume Information" | "C:\Apps (x86)\SysTools\UnxUtils\usr\local\wbin\tee.exe" "C:\Users\paulm\Desktop\d_drive.stdout.txt"

# HTPC e
#C:\Apps\Dev\Python36\python.exe -u "C:\Users\elrond\Desktop\RecursiveHashCompare\recursiveHashCompare.py" "E:" --add-date "C:\Users\elrond\Desktop\e_drive"  -i 60 --exclude "System Volume Information" --exclude "\$RECYCLE.BIN" --exclude "dbc507b1a818424ae9bede9f" --exclude "msdownld\.tmp" --exclude "\.DS_Store" | "C:\Apps (x86)\SysTools\UnxUtils\usr\local\wbin\tee.exe" "C:\Users\elrond\Desktop\e_drive.stdout.txt"

# test - takes ~?? seconds single-threaded
#C:\Apps\DevTools\Python36\python.exe -u "D:\Dev\Projects\RecursiveHashCompare\recursiveHashCompare.py" D:\Dev\Projects\__Archive\3D D:\devProjectsArchive3D.txt -i 1

# test - takes ~15 seconds single-threaded
#C:\Apps\DevTools\Python36\python.exe -u "D:\Dev\Projects\RecursiveHashCompare\recursiveHashCompare.py" D:\Dev\Projects\__Archive D:\devProjectsArchive.txt -i 1

# test - takes ~?? seconds single-threaded
#C:\Apps\DevTools\Python36\python.exe -u "D:\Dev\Projects\RecursiveHashCompare\recursiveHashCompare.py" D:\Dev\Projects\ D:\devProjects.txt -i 1


import argparse
import binascii
import datetime
import hashlib
import os
import pathlib
import re
import sys
import traceback
import signal

from pathlib import Path

import gevent.monkey
gevent.monkey.patch_all()
from gevent.pool import Pool
from gevent.queue import Queue, Empty
from gevent.lock import BoundedSemaphore


SUMMARY_EXTRA = ".summary"
SUMMARY_DEPTH_DEFAULT = 3
DEFAULT_INTERVAL = 10
DEFAULT_BUFFER_SIZE = 4096
LONGPATH_PREFIX = '\\\\?\\'
ERROR_HASH = binascii.a2b_hex('bad00000000000000000000000000000')
ENCODING = 'utf8'
DEFAULT_THREADS = 200


class Updater(object):
    def __init__(self, interval=datetime.timedelta(seconds=DEFAULT_INTERVAL)):
        self.start = datetime.datetime.now()
        self.last = self.start
        if not isinstance(interval, datetime.timedelta):
            interval = datetime.timedelta(seconds=interval)
        self.interval = interval

    def update_progress(self, *args, **kwargs):
        pass

    def start_updates(self):
        pass

    def end_updates(self):
        pass

class DirQueueItem(object):
    def __init__(self, folder, parent):
        # print(f"DirQueueItem({folder!r}")
        self.folder = folder
        self.parent = parent
        self.dirHashData = None
        self.results = None
        self.numResults = None
        self.resultsLock = None

    def setNumResults(self, numResults):
        self.numResults = numResults
        self.resultsLock = BoundedSemaphore()
        self.results = []

    def addResult(self, result):
        '''Add a result on this directory's result list, and return a bool
        indicating whether all results have been added'''
        self.resultsLock.acquire()
        try:
            self.results.append(result)
            return len(self.results) == self.numResults
        finally:
            self.resultsLock.release()

    def isDone(self):
        # only needed by the top-level entry, created in start_dir_crawl - all
        # other DirQueueItems will know they're done because a child will
        # call addResult on it's parent, and get a non-None result back
        if self.resultsLock is None:
            return False
        self.resultsLock.acquire()
        try:
            return len(self.results) == self.numResults
        finally:
            self.resultsLock.release()


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


    def relpath(self, subpath=None):
        if subpath is None:
            subpath = self.path_obj
        root_path = self.get_short_path(self.root_dir.path_obj)
        path = self.get_short_path(subpath)
        return str(path.relative_to(root_path))


class FileHashData(BaseHashData):
    def __init__(self, filepath, updater=None, root_dir=None):
#        print(f"FileHashData({filepath!r}")

        self.root_dir = root_dir
        self.error = None
        self.hash = None
        self.size = 0
        try:
            self.set_path(filepath)
            stat = self.path_obj.stat()

            self.size = stat.st_size
            filehash = hashlib.md5()

            if hasattr(stat, 'st_blksize') and stat.st_blksize:
                buffer_size = stat.st_blksize
            else:
                buffer_size = DEFAULT_BUFFER_SIZE
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
    def __init__(self, files, updater=None, root_dir=None):
        self.files = []

        running_hash = hashlib.md5()
        self.size = 0
        for i, filehash in enumerate(files):
            if not isinstance(filehash, FileHashData):
                filehash = FileHashData(filehash, updater=updater,
                                        root_dir=root_dir)
            self.files.append(filehash)
            self.size += filehash.size
            running_hash.update(os.path.basename(filehash.path_str)
                                .encode(ENCODING))
            running_hash.update(filehash.hash)

        self.hash = running_hash.digest()

    def strlines(self, indent_level):
        yield '{}<files> - {:,} - {}'.format(self.INDENT * indent_level,
            self.size, self.hexhash())
        for filedata in self.files:
            for line in filedata.strlines(indent_level + 1):
                yield line


class DirHashData(BaseHashData):
    def __init__(self, dirQueueItem, dirQueue, updater=None, exclude=None,
                 root_dir=None):
        if dirQueueItem.parent is None:
            self.root_dir = self
        else:
            self.root_dir = dirQueueItem.parent.dirHashData.root_dir
        self.exclude = exclude
        self.set_path(dirQueueItem.folder)
        dirQueueItem.dirHashData = self
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

        self.size = 0
        self.running_hash = hashlib.md5()

        self.files = FilesHashData(subfiles, updater=updater, root_dir=root_dir)

        self.size += self.files.size
        self.running_hash.update(self.files.hash)

        dirQueueItem.setNumResults(len(subfolders))
        if subfolders:
            for subfolder in subfolders:
                dirQueue.put(DirQueueItem(subfolder, dirQueueItem))
        else:
            self.finishHashing(dirQueueItem)

    def finishHashing(self, dirQueueItem):
        # we should only be called if dirQueueItem is good to go
        assert(len(dirQueueItem.results) == dirQueueItem.numResults)

        self.dirs = dirQueueItem.results
        self.dirs.sort(key=lambda x: x.path_str)

        for subdirdata in self.dirs:
            self.size += subdirdata.size
            self.running_hash.update(subdirdata.path_obj.name.encode(ENCODING))
            self.running_hash.update(subdirdata.hash)
        self.hash = self.running_hash.digest()
        del self.running_hash

        if (dirQueueItem.parent is not None):
            if (dirQueueItem.parent.addResult(self)):
                dirQueueItem.parent.dirHashData.finishHashing(dirQueueItem.parent)

    def is_excluded(self, path):
        if not self.root_dir.exclude:
            return False
        rel_path = self.relpath(path)
        for exclusion_re in self.root_dir.exclude:
            if exclusion_re.match(rel_path):
                return True
        return False

    def strlines(self, indent_level):
        if self.root_dir is self:
            pathname = self.path_str
        else:
            pathname = self.relpath()
        yield '{}{} - {:,} - {}'.format(self.INDENT * indent_level,
            pathname, self.size, self.hexhash())
        for line in self.files.strlines(indent_level + 1):
            yield line
        for dirdata in self.dirs:
            for line in dirdata.strlines(indent_level + 1):
                yield line


def start_dir_crawl(folder, interval=DEFAULT_INTERVAL, exclude=(),
                    num_threads=DEFAULT_THREADS):
    if interval > 0:
        updater = Updater(interval)
    else:
        updater = None

    if isinstance(exclude, str):
        exclude = [exclude]
    exclude = [x if isinstance(x, re._pattern_type)
               else re.compile(x) for x in exclude]

    pool = Pool(num_threads)
    dirQueue = Queue()
    topDirItem = DirQueueItem(folder, None)
    dirQueue.put(topDirItem)

    while True:
        try:
            nextDirItem = dirQueue.get_nowait()
        except Empty:
            if topDirItem.isDone():
                break
            else:
                gevent.sleep(1)
        else:
            pool.spawn(DirHashData, nextDirItem, dirQueue, exclude=exclude)

    return topDirItem.dirHashData


def write_hashes(folder, output_txt, interval=DEFAULT_INTERVAL, exclude=(),
                 add_date=False, num_threads=DEFAULT_THREADS):
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
    output_txt = str(ensure_slash_after_drive(output_txt))

    if add_date:
        output_base, output_ext = os.path.splitext(output_txt)
        output_txt = output_base + datetime.date.today().strftime('.%Y-%m-%d') \
            + output_ext

    # we do a test open of both output paths to make sure they're writable
    # before doing whole crawl!
    with open(output_txt, 'a') as f:
        pass

    print(f"Crawling directory {folder}...")
    start = datetime.datetime.now()
    dirdata = start_dir_crawl(folder, interval=interval, exclude=exclude,
                              num_threads=num_threads)
    elapsed = datetime.datetime.now() - start
    print(f"Done crawling directory {folder}! (took {elapsed})")

    print(f"Writing text data to {output_txt}...")
    with open(output_txt, 'w', encoding=ENCODING) as f:
        f.write(f'# -*- coding: {ENCODING} -*-\n\n')
        for line in dirdata.strlines(0):
            f.write(line)
            f.write('\n')
    print(f"Done writing text data to {output_txt}!")


def get_parser():
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('dir',
        help='Directory to generate hash for - default to current directory',
        default=".")
    parser.add_argument('output',
        help='Path to output text file to generate output hash information in',
        default="md5_hashes")
    parser.add_argument('-i', '--interval', type=int, default=DEFAULT_INTERVAL,
        help="How often to print out progress updates, in seconds; set to 0"
            " in order to disable updates")
    parser.add_argument('-e', '--exclude', action='append', default=[],
        help="Regular expression for paths to exclude (relative to base DIR);"
             " may be given multiple times")
    parser.add_argument('-d', '--add-date', action='store_true',
        help='If set, then a date string will be added to the end of the OUTPUT'
             ' filename given (before the extension)')
    parser.add_argument('-t', '--threads', default=DEFAULT_THREADS, type=int,
        help='Number of concurrent tasks to run')
    return parser


def main(args=sys.argv[1:]):
    parser = get_parser()
    args = parser.parse_args(args)
    write_hashes(args.dir, args.output, interval=args.interval,
                 exclude=args.exclude, add_date=args.add_date,
                 num_threads=args.threads)


if __name__ == '__main__':
    main()
