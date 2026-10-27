"""Standard-library snapshot, lock and immutable publication primitives."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
import tempfile
import uuid


class BuildError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise BuildError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def constant(value):
        raise BuildError('Nonfinite JSON value: ' + value)
    def floating(value):
        import math
        result = float(value)
        if not math.isfinite(result):
            raise BuildError('Nonfinite JSON number')
        return result
    return json.loads(data.decode('utf-8-sig') if isinstance(data, bytes) else data,
                      object_pairs_hook=pairs, parse_constant=constant, parse_float=floating)


def no_symlinks(path):
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        try:
            attributes = getattr(item.lstat(), 'st_file_attributes', 0)
        except FileNotFoundError:
            attributes = 0
        if item.is_symlink() or attributes & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0):
            raise BuildError('Symbolic link or junction is not permitted: ' + str(item))
    return path


def owned_directory(path):
    """Create only missing directories, with public traversal on POSIX."""
    path = no_symlinks(path)
    missing = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    for item in reversed(missing):
        item.mkdir()
        if os.name == 'posix':
            os.chmod(item, 0o755, follow_symlinks=False)


def checked_output(root, output):
    root = no_symlinks(root).resolve(strict=True)
    output = no_symlinks(output).resolve()
    code_root = Path(__file__).resolve().parent.parent
    if output.is_relative_to(code_root) or code_root.is_relative_to(output):
        raise BuildError('Output cannot overlap the builder tools directory')
    if output == root or root.is_relative_to(output):
        raise BuildError('Output cannot contain the source repository')
    if output.is_relative_to(root) and output != root / 'cache':
        raise BuildError('Output inside source root must be its cache directory')
    if output.exists() and not output.is_dir():
        raise BuildError('Output must be a directory')
    return output


class Snapshot:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        self.files = {}
        self.code_labels = {}
        self.code_directories = {}
        self.directories = {}

    def _path(self, path):
        path = no_symlinks(path)
        if not path.resolve().is_relative_to(self.root):
            raise BuildError('Input escapes source root: ' + str(path))
        return path

    def read(self, path):
        path = self._path(path)
        data = path.read_bytes()
        sha = digest(data)
        if path in self.files and self.files[path] != sha:
            raise BuildError('Input changed during build: ' + str(path))
        self.files[path] = sha
        return data

    def read_code(self, path, label):
        path = no_symlinks(path).resolve(strict=True)
        data = path.read_bytes()
        sha = digest(data)
        if path in self.files and self.files[path] != sha:
            raise BuildError('Builder code changed during build: ' + str(path))
        self.files[path] = sha
        self.code_labels[path] = label
        return data

    def track_code_directory(self, path, label):
        path = no_symlinks(path).resolve(strict=True)
        self.code_directories[path] = (label, tuple(sorted(p.name for p in path.glob('*.py'))))

    def read_optional(self, path):
        path = self._path(path)
        if path.exists():
            return self.read(path)
        if path in self.files and self.files[path] is not None:
            raise BuildError('Input disappeared during build: ' + str(path))
        self.files[path] = None
        return None

    def track_resolution(self, paths):
        return [self.read_optional(path) for path in paths]

    def _members(self, path, pattern):
        no_symlinks(path)
        return tuple(sorted(str(no_symlinks(p).relative_to(self.root)).replace('\\', '/')
                            for p in path.glob(pattern)))

    def track_directory(self, path, pattern):
        path = self._path(path)
        key = (path, pattern)
        members = self._members(path, pattern)
        if key in self.directories and self.directories[key] != members:
            raise BuildError('Directory changed during build: ' + str(path))
        self.directories[key] = members
        return members

    def verify(self):
        for path, expected in self.files.items():
            no_symlinks(path)
            actual = digest(path.read_bytes()) if path.exists() else None
            if actual != expected:
                raise BuildError('Input changed during build: ' + str(path))
        for (path, pattern), expected in self.directories.items():
            if self._members(path, pattern) != expected:
                raise BuildError('Directory changed during build: ' + str(path))
        for path, (_, expected) in self.code_directories.items():
            no_symlinks(path)
            if tuple(sorted(p.name for p in path.glob('*.py'))) != expected:
                raise BuildError('Builder code set changed during build: ' + str(path))

    def signature(self):
        files = sorted((self.code_labels[p] if p in self.code_labels else p.relative_to(self.root).as_posix(), sha)
                       for p, sha in self.files.items())
        directories = sorted((p.relative_to(self.root).as_posix(), pat, members)
                             for (p, pat), members in self.directories.items())
        code_directories = sorted(self.code_directories.values())
        return digest(json.dumps([files, directories, code_directories], ensure_ascii=False,
                                 separators=(',', ':'), sort_keys=True).encode('utf-8'))


class Publication:
    def __init__(self, root, output):
        self.output = checked_output(root, output)
        self.lock = self.output / '.build.lock'
        self.token = (str(os.getpid()) + ':' + uuid.uuid4().hex).encode('ascii')
        self.written = 0
        self.previous_catalogue = None

    def _existing_catalogue(self):
        path = no_symlinks(self.output / 'catalogue.json')
        if not path.exists():
            return None
        data = path.read_bytes()
        document = strict_json(data)
        if (not isinstance(document, dict)
                or document.get('schema') != 'aldbrowser-catalogue-v1'
                or not isinstance(document.get('pages'), list)
                or any(not isinstance(page, dict) or not isinstance(page.get('id'), str)
                       or not isinstance(page.get('url'), str) for page in document['pages'])):
            raise BuildError('Existing catalogue is not an owned browser cache')
        return digest(data)

    def __enter__(self):
        owned_directory(self.output)
        no_symlinks(self.output)
        self.previous_catalogue = self._existing_catalogue()
        try:
            descriptor = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(self.token)
        except FileExistsError as error:
            raise BuildError('Build lock exists; another build may be active: ' + str(self.lock)) from error
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.lock.exists() and not self.lock.is_symlink() and self.lock.read_bytes() == self.token:
            self.lock.unlink()

    def _temporary(self, folder, data):
        descriptor, name = tempfile.mkstemp(prefix='.building-', dir=folder)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                if os.name == 'posix':
                    os.fchmod(stream.fileno(), 0o644)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            Path(name).unlink(missing_ok=True)
            raise
        return Path(name)

    def put_asset(self, data, suffix):
        if suffix not in ('.txt', '.json') or not isinstance(data, bytes):
            raise BuildError('Invalid static asset')
        folder = self.output / 'assets'
        no_symlinks(folder)
        owned_directory(folder)
        relative = 'assets/' + digest(data) + suffix
        target = self.output / relative
        no_symlinks(target)
        if target.exists():
            if target.read_bytes() != data:
                raise BuildError('Existing content-addressed asset has wrong bytes: ' + str(target))
            return relative
        temporary = self._temporary(folder, data)
        try:
            try:
                os.link(temporary, target)
                self.written += 1
            except FileExistsError:
                if target.read_bytes() != data:
                    raise BuildError('Content-addressed asset collision')
        finally:
            temporary.unlink(missing_ok=True)
        return relative

    def publish(self, catalogue, snapshot):
        payload = (json.dumps(catalogue, ensure_ascii=False, sort_keys=True,
                              indent=2, allow_nan=False) + '\n').encode('utf-8')
        target = self.output / 'catalogue.json'
        no_symlinks(target)
        if self._existing_catalogue() != self.previous_catalogue:
            raise BuildError('Published catalogue changed during build')
        snapshot.verify()
        if target.exists() and target.read_bytes() == payload:
            return False, digest(payload)
        temporary = self._temporary(self.output, payload)
        try:
            snapshot.verify()
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return True, digest(payload)
