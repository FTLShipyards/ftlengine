from cStringIO import StringIO
import json
import os.path
import struct
import tarfile

try:
    from docker.constants import STREAM_HEADER_SIZE_BYTES
except ImportError:
    # Docker-py<1.2
    from docker.client import STREAM_HEADER_SIZE_BYTES


class DockerTarStream(object):
    def __init__(self, stream):
        # We need to read into a StringIO, because tarfile does random I/O (stupic, I know)
        file = StringIO(stream.read())
        self.tar = tarfile.open(fileobj=file)

    def __getitem__(self, name):
        return self.tar.extractfile(os.path.basename(name)).read()


class DockerJSONStream(object):
    def __init__(self, stream):
        self.stream = stream

    def __iter__(self):
        for entry in self.stream:
            for chunk in entry.split('\n'):
                if chunk.strip():
                    try:
                        data = json.loads(chunk.strip())
                    except ValueError as e:
                        raise ValueError('Could not decode docker JSON stream entry: %r (%s)' % (entry, e))
                    yield data


class DockerRawStream(object):
    def __init__(self, stream):
        sock = stream._fp.fp._sock
        sock.settimeout(None)
        self.stream = stream

    def __iter__(self):
        while True:
            header = self.stream.read(STREAM_HEADER_SIZE_BYTES)
            if not header:
                break
            _, length = struct.unpack_from('>BxxxL', header)
            data = self.stream.read(length)
            if not data:
                break
            yield data
