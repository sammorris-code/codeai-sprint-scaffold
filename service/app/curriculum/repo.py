"""Reading the upstream curriculum repository.

**Everything is read out of git object storage. Nothing is read from a working
tree, and nothing is ever written upstream.**

That is not a preference. A working tree cannot hold this repository on
Windows. `dashboard/config/levels/` contains file names with `:` and `?` in
them, which NTFS forbids, so `git checkout` refuses 512 paths and abandons the
whole directory. It then exits 0. An extractor reading the working tree would
report success and find no student instructions at all — which is the same
silent undercount the briefing warns about, arriving by a different route.

Reading blobs instead removes the filesystem from the problem. It also buys
two things worth having on their own:

  - The read is pinned to one commit. That is exactly what `snapshot.source_commit`
    records, so a claim can always be traced to the curriculum it was made against.
  - It behaves the same on every machine, so a contractor on Windows and a
    server on Linux extract the same corpus.

One operational note. Clone shallow but **do not** use `--filter=blob:none`.
A blobless clone fetches each blob on demand, and the demand here is tens of
thousands of small files one at a time. Hydrating them in a single pack up
front turns hours into seconds. See `docs/` in the service README.
"""
import subprocess
import threading

# Every upstream path lives here, and only here. Engineering has discussed
# moving curriculum content out of the main repository — the seeding task
# already reads it from an overridable directory variable — so when that
# happens this constant is the part that changes.
CONTENT_DIR = "dashboard/config"

SUBDIRS = {
    "courses": f"{CONTENT_DIR}/courses",
    "course_offerings": f"{CONTENT_DIR}/course_offerings",
    "units": f"{CONTENT_DIR}/scripts_json",
    "standards": f"{CONTENT_DIR}/standards",
    # The two places level content hides. Both are needed; see levels.py.
    "levels_xml": f"{CONTENT_DIR}/levels",
    "levels_dsl": f"{CONTENT_DIR}/scripts",
}


class MissingBlob(Exception):
    """A path the tree listed but the object store could not produce.

    Almost always means the clone was made with --filter=blob:none and the
    blob was never fetched. Raised rather than returned as empty, because an
    empty lesson that looks like a real one is the failure this whole module
    exists to prevent.
    """


class Repo:
    """One pinned read-only view of the upstream repository.

    Used as a context manager so the long-running `cat-file` process is always
    cleaned up:

        with Repo(path) as repo:
            repo.read_text(some_path)
    """

    def __init__(self, path, rev="HEAD"):
        self.path = str(path)
        self.commit = self._git("rev-parse", rev).decode().strip()
        self._batch = None

    # -- plumbing ---------------------------------------------------------

    def _git(self, *args):
        done = subprocess.run(["git", *args], cwd=self.path,
                              capture_output=True)
        if done.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed in {self.path}\n"
                f"{done.stderr.decode('utf-8', 'replace')}")
        return done.stdout

    def _start_batch(self):
        # One process answers every read. Starting git per file is the
        # difference between seconds and an afternoon.
        self._batch = subprocess.Popen(
            ["git", "cat-file", "--batch"], cwd=self.path,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    # -- reading ----------------------------------------------------------

    def list(self, subdir_key, suffixes=None):
        """Every path under one subdirectory, from the tree, not the disk.

        `suffixes` filters by extension. Order is git's, which is stable for a
        given commit, so a corpus rebuilt from the same commit is byte-identical.
        """
        prefix = SUBDIRS[subdir_key]
        out = self._git("ls-tree", "-r", "--name-only", self.commit, prefix)
        paths = [p for p in out.decode("utf-8", "replace").splitlines() if p]
        if suffixes:
            paths = [p for p in paths if p.endswith(tuple(suffixes))]
        return paths

    def read(self, path):
        """The bytes of one blob at the pinned commit."""
        if self._batch is None:
            self._start_batch()
        self._batch.stdin.write(f"{self.commit}:{path}\n".encode())
        self._batch.stdin.flush()
        header = self._batch.stdout.readline().decode("utf-8", "replace").split()
        # git answers a bad request with "<what you asked> missing".
        if len(header) < 3 or header[-1] in ("missing", "ambiguous"):
            raise MissingBlob(path)
        size = int(header[2])
        body = self._read_exactly(size)
        self._batch.stdout.read(1)          # the newline git adds after a blob
        return body

    def read_text(self, path):
        # 'replace' rather than 'strict': one bad byte in one level should not
        # end an extraction of 300 lessons. Curriculum text is full of smart
        # quotes and emoji and is not always clean UTF-8.
        return self.read(path).decode("utf-8", "replace")

    def read_many(self, paths):
        """Read a batch of paths, yielding (path, text).

        Pipelined, so the cost is one round trip rather than one per file.
        This is what makes indexing 36,000 DSL files take seconds.

        The requests are written by a separate thread on purpose. Writing all
        of them first and only then reading deadlocks: git fills its output
        pipe after about 64KB and stops, we are still trying to write to its
        input pipe, and neither side can move. It looks exactly like a slow
        network, which is a bad thing for a bug to look like.
        """
        if not paths:
            return
        if self._batch is None:
            self._start_batch()

        def feed():
            try:
                for p in paths:
                    self._batch.stdin.write(f"{self.commit}:{p}\n".encode())
                self._batch.stdin.flush()
            except (BrokenPipeError, ValueError):
                pass

        writer = threading.Thread(target=feed, daemon=True)
        writer.start()
        try:
            for p in paths:
                header = self._batch.stdout.readline().decode("utf-8", "replace").split()
                if len(header) < 3 or header[-1] in ("missing", "ambiguous"):
                    raise MissingBlob(p)
                size = int(header[2])
                body = self._read_exactly(size)
                self._batch.stdout.read(1)
                yield p, body.decode("utf-8", "replace")
        finally:
            writer.join(timeout=5)

    def _read_exactly(self, size):
        """A pipe read can come back short. Keep going until it does not."""
        chunks = []
        left = size
        while left > 0:
            chunk = self._batch.stdout.read(left)
            if not chunk:
                break
            chunks.append(chunk)
            left -= len(chunk)
        return b"".join(chunks)

    # -- lifecycle --------------------------------------------------------

    def close(self):
        if self._batch is not None:
            self._batch.stdin.close()
            self._batch.wait()
            self._batch = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
