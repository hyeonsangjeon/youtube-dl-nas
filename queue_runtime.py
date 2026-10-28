"""The queue, history and media operations the collections backend may use.

The web server owns the download queue, the history file and the yt-dlp worker.
The collections backend plans and tracks batches on top of them. It used to receive
the server module's whole ``globals()`` dict and reach back through string keys, so
nothing showed which server functions it depended on, and renaming one broke the
backend only at run time. ``QueueRuntime`` writes that dependency down: one method
per operation, and the full set is checked when the server starts.

The server hands over zero-argument providers, not values. Every call asks the
provider again, so the backend always sees live state (the active job changes while
a download runs) and tests can still replace a server function after start-up.
"""


class QueueRuntime:
    """Explicit boundary between the web server and the collections backend."""

    OPERATIONS = frozenset({
        # Locks and live queue state.
        "queue_operation_lock",
        "queue_state_lock",
        "active_queue_job",
        "download_dir",
        # Queue jobs.
        "normalize_queue_job",
        "same_queue_request",
        "pending_queue_jobs",
        "create_queue_job",
        "find_queued_duplicate",
        "apply_collection_queue_journal",
        "start_download_thread_if_needed",
        # Download history.
        "normalize_history_item",
        "find_existing_download",
        "normalized_history",
        "combined_history",
        "broadcast",
        # Source validation and metadata.
        "validate_download_request",
        "validate_source_redirects",
        "get_error_details",
        "classify_playlist_url",
        "normalize_media_url",
        "fetch_media_metadata",
        "get_media_identity",
        "get_media_display_title",
        "get_storage_status",
    })

    __slots__ = ("_providers",)

    def __init__(self, **providers):
        missing = sorted(self.OPERATIONS - providers.keys())
        unknown = sorted(providers.keys() - self.OPERATIONS)
        not_callable = sorted(name for name, provider in providers.items() if not callable(provider))
        problems = []
        if missing:
            problems.append("missing " + ", ".join(missing))
        if unknown:
            problems.append("unknown " + ", ".join(unknown))
        if not_callable:
            problems.append("not callable " + ", ".join(not_callable))
        if problems:
            raise TypeError("QueueRuntime providers: " + "; ".join(problems))
        self._providers = dict(providers)

    def _current(self, name):
        return self._providers[name]()

    # Locks and live queue state.

    @property
    def queue_operation_lock(self):
        """Re-entrant lock that serializes every queue mutation."""
        return self._current("queue_operation_lock")

    @property
    def queue_state_lock(self):
        """Lock that guards the active job and the persisted queue snapshot."""
        return self._current("queue_state_lock")

    def active_queue_job(self):
        """The job the worker is running now, or None. Read under queue_state_lock."""
        return self._current("active_queue_job")

    def download_dir(self):
        """Absolute or relative path of the download root (``DOWNLOAD_DIR``)."""
        return self._current("download_dir")

    # Queue jobs.

    def normalize_queue_job(self, item, restored=False):
        return self._current("normalize_queue_job")(item, restored=restored)

    def same_queue_request(self, first, second):
        return self._current("same_queue_request")(first, second)

    def pending_queue_jobs(self):
        return self._current("pending_queue_jobs")()

    def create_queue_job(self, url, resolution, source, **options):
        return self._current("create_queue_job")(url, resolution, source, **options)

    def find_queued_duplicate(self, job):
        return self._current("find_queued_duplicate")(job)

    def apply_collection_queue_journal(self, jobs, terminal_job_ids=()):
        return self._current("apply_collection_queue_journal")(jobs, terminal_job_ids)

    def start_download_thread_if_needed(self):
        return self._current("start_download_thread_if_needed")()

    # Download history.

    def normalize_history_item(self, item):
        return self._current("normalize_history_item")(item)

    def find_existing_download(self, url, resolution, **options):
        return self._current("find_existing_download")(url, resolution, **options)

    def normalized_history(self):
        return self._current("normalized_history")()

    def combined_history(self):
        return self._current("combined_history")()

    def broadcast(self, message):
        """Send one WebSocket message to every connected dashboard."""
        return self._current("broadcast")(message)

    # Source validation and metadata.

    def validate_download_request(self, url, resolution, **options):
        return self._current("validate_download_request")(url, resolution, **options)

    def validate_source_redirects(self, url):
        return self._current("validate_source_redirects")(url)

    def get_error_details(self, message):
        return self._current("get_error_details")(message)

    def classify_playlist_url(self, value):
        return self._current("classify_playlist_url")(value)

    def normalize_media_url(self, value):
        return self._current("normalize_media_url")(value)

    def fetch_media_metadata(self, url, **options):
        return self._current("fetch_media_metadata")(url, **options)

    def get_media_identity(self, metadata):
        return self._current("get_media_identity")(metadata)

    def get_media_display_title(self, metadata, fallback):
        return self._current("get_media_display_title")(metadata, fallback)

    def get_storage_status(self):
        return self._current("get_storage_status")()
