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


import os
import sys
import argparse
import pathlib
import hashlib
import binascii
import datetime
import pickle


from pathlib import Path


SUMMARY_EXTRA = ".summary"
SUMMARY_DEPTH_DEFAULT = 3
DEFAULT_INTERVAL=10


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


class FileHashData(BaseHashData):
    def __init__(self, filepath, updater=None, progress=None):
        if not isinstance(filepath, pathlib.Path):
            filepath = pathlib.Path(filepath)
        if updater:
            if not progress:
                progress = []
            updater.update(filepath, progress)

        self.path = str(filepath)
        self.size = filepath.stat().st_size
        filehash = hashlib.md5()
        filehash.update(filepath.read_bytes())
        self.hash = filehash.digest()         

    def strlines(self, indent_level):
        return ['{}{} - {:,} - {}'.format(self.INDENT * indent_level,
            os.path.basename(self.path), self.size, self.hexhash())]
    

class FilesHashData(BaseHashData):
    def __init__(self, files, updater=None, progress=None):
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
                    progress=new_progress)
            self.files.append(filehash)
            self.size += filehash.size
            running_hash.update(os.path.basename(filehash.path).encode('utf8'))
            running_hash.update(filehash.hash)
        self.hash = running_hash.digest()

    def strlines(self, indent_level):
        yield '{}<files> - {:,} - {}'.format(self.INDENT * indent_level,
            self.size, self.hexhash())
        for filedata in self.files:
            for line in filedata.strlines(indent_level + 1):
                yield line


class DirHashData(BaseHashData):
    def __init__(self, folderpath, updater=None, progress=None):
        if not isinstance(folderpath, pathlib.Path):
            folderpath = pathlib.Path(folderpath)
        if updater:
            if not progress:
                progress = []
            updater.update(folderpath, progress)
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
        
        self.files = FilesHashData(subfiles, updater=updater, progress=progress)

        self.size += self.files.size
        running_hash.update(self.files.hash)

        self.dirs = []
        for i, subfolder in enumerate(subfolders):
            if updater:
                new_progress = progress + [(i + 1, len(subfolders))]
            else:
                new_progress = None
            subdirdata = type(self)(subfolder, updater=updater,
                progress=new_progress)
            self.dirs.append(subdirdata)
            self.size += subdirdata.size
            running_hash.update(subfolder.name.encode('utf8'))
            running_hash.update(subdirdata.hash)
        self.hash = running_hash.digest()

    def strlines(self, indent_level):
        yield '{}{} - {:,} - {}'.format(self.INDENT * indent_level,
            os.path.basename(self.path), self.size, self.hexhash())
        for dirdata in self.dirs:
            for line in dirdata.strlines(indent_level + 1):
                yield line
        for line in self.files.strlines(indent_level + 1):
            yield line


def write_hashes(folder, output_path, interval=DEFAULT_INTERVAL):
    if interval > 0:
        updater = Updater(interval)
    else:
        updater = None
    dirdata = DirHashData(folder, updater=updater)

    output_base, output_ext = os.path.splitext(output_path)
    if output_ext == '.txt':
        output_txt = output_path
        output_pickle = output_base + '.pickle'
    else:
        output_pickle = output_path
        output_txt = output_base + '.txt'

    with open(output_pickle, 'wb') as f:
        pickle.dump(dirdata, f, protocol=pickle.HIGHEST_PROTOCOL)

    with open(output_txt, 'w') as f:
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
    return parser


def main(args=sys.argv[1:]):
    parser = get_parser()
    args = parser.parse_args(args)
    write_hashes(args.dir, args.output, interval=args.interval)


if __name__ == '__main__':
    main()