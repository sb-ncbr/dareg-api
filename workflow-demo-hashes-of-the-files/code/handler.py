"""
A lambda which calculates (and saves as metadata) file and folder checksum using REST interface.
"""

__author__ = "Bartosz Walkowicz"
__copyright__ = "Copyright (C) 2022 ACK CYFRONET AGH"
__license__ = "This software is released under the MIT license cited in LICENSE.txt"
__note__= "Part of the Onedata project. Coauthor Filip Bugos"

import concurrent.futures
import hashlib
import os
import queue
import sys
import traceback
import zlib
from threading import Event, Thread
from typing import (
    Final,
    FrozenSet,
    Iterator,
    Literal,
    NamedTuple,
    Optional,
    Union,
    get_args,
)

import requests

from onedata_lambda_utils.stats import AtmTimeSeriesMeasurementBuilder
from onedata_lambda_utils.streaming import AtmResultStreamer
from onedata_lambda_utils.types import (
    AtmException,
    AtmFile,
    AtmHeartbeatCallback,
    AtmJobBatchRequest,
    AtmJobBatchRequestCtx,
    AtmJobBatchResponse,
    AtmTimeSeriesMeasurement,
)

if sys.version_info < (3, 11):
    from typing_extensions import TypeAlias, TypedDict
else:
    from typing import TypeAlias, TypedDict


##===================================================================
## Lambda configuration
##===================================================================


DOWNLOAD_CHUNK_SIZE: Final[int] = 10 * 1024**2
VERIFY_SSL_CERTS: Final[bool] = os.getenv("VERIFY_SSL_CERTIFICATES") != "false"
REST_REQUEST_TIMEOUT: Final[int] = 60
EXTENDED_REST_REQUEST_TIMEOUT: Final[int] = 120


##===================================================================
## Lambda interface
##===================================================================


STATS_STREAMER: Final[AtmResultStreamer[AtmTimeSeriesMeasurement]] = AtmResultStreamer(
    result_name="stats", synchronized=False
)


class FilesProcessed(
    AtmTimeSeriesMeasurementBuilder, ts_name="filesProcessed", unit=None
):
    pass


class BytesProcessed(
    AtmTimeSeriesMeasurementBuilder, ts_name="bytesProcessed", unit="Bytes"
):
    pass


ChecksumAlgorithm: TypeAlias = Literal[
    "adler32",
    "blake2b",
    "blake2s",
    "md5",
    "sha1",
    "sha224",
    "sha256",
    "sha384",
    "sha512",
    "sha3_224",
    "sha3_256",
    "sha3_384",
    "sha3_512",
    "shake_128",
    "shake_256",
]


AVAILABLE_CHECKSUM_ALGORITHMS: Final[FrozenSet[ChecksumAlgorithm]] = frozenset(
    get_args(ChecksumAlgorithm)
)


class TaskConfig(TypedDict):
    algorithm: ChecksumAlgorithm
    metadataKey: str


class JobArgs(TypedDict):
    file: AtmFile


class FileChecksumReport(TypedDict):
    fileId: str
    algorithm: str
    checksum: Optional[str]


class JobResults(TypedDict):
    result: FileChecksumReport


##===================================================================
## Lambda implementation
##===================================================================


class Job(NamedTuple):
    ctx: AtmJobBatchRequestCtx[TaskConfig]
    args: JobArgs


_all_jobs_processed: Event = Event()
_measurements_queue: queue.Queue = queue.Queue()


def handle(
    job_batch_request: AtmJobBatchRequest[JobArgs, TaskConfig],
    heartbeat_callback: AtmHeartbeatCallback,
) -> Union[AtmException, AtmJobBatchResponse[JobResults]]:
    algorithm = job_batch_request["ctx"]["config"]["algorithm"]
    if algorithm not in AVAILABLE_CHECKSUM_ALGORITHMS:
        return AtmException(
            exception=(
                f"{algorithm} algorithm is unsupported. "
                f"Available ones are: {AVAILABLE_CHECKSUM_ALGORITHMS}"
            )
        )

    jobs_monitor = Thread(target=monitor_jobs, daemon=True, args=[heartbeat_callback])
    jobs_monitor.start()

    jobs = [
        Job(args=job_args, ctx=job_batch_request["ctx"])
        for job_args in job_batch_request["argsBatch"]
    ]
    with concurrent.futures.ThreadPoolExecutor() as executor:
        job_results = list(executor.map(run_job, jobs))

    _all_jobs_processed.set()
    jobs_monitor.join()

    return {"resultsBatch": job_results}


def run_job(job: Job) -> Union[AtmException, JobResults]:
    file_type = job.args["file"].get("type")
    print("=== run_job called ===")
    print(f"fileId: {job.args['file'].get('fileId')}")
    print(f"type: {file_type}")
    print(f"domain: {job.ctx.get('oneproviderDomain')}")
    try:
        algorithm = job.ctx["config"]["algorithm"]
        print(f"algorithm: {algorithm}")
        if file_type == "REG":
            print("Processing REG file")
            data_stream = get_file_data_stream(job)
            checksum = calculate_checksum(algorithm, data_stream)
        elif file_type == "DIR":
            print("Processing DIR file")
            checksum = calculate_dir_checksum(job, algorithm)
        else:
            print("Unknown file type")
            checksum = None

        xattr_name = job.ctx["config"].get("metadataKey")
        print(f"xattr_name: {xattr_name}")
        print(f"checksum: {checksum}")
        if checksum and xattr_name:
            set_file_xattr(job, xattr_name, checksum)
    except requests.RequestException as ex:
        print(f"RequestException: {ex}")
        return AtmException(exception=str(ex))
    except Exception:
        print(f"Exception: {traceback.format_exc()}")
        return AtmException(exception=traceback.format_exc())
    else:
        print("run_job completed successfully")
        return build_job_results(job, checksum)
    finally:
        _measurements_queue.put(FilesProcessed.build(value=1))

def list_dir_children(job: Job) -> list:
    """List child files and folders for a DIR using Oneprovider REST API."""
    url = build_file_rest_url(job, "children")
    response = requests.get(
        url,
        headers={"x-auth-token": job.ctx["accessToken"]},
        verify=VERIFY_SSL_CERTS,
        timeout=EXTENDED_REST_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json().get("children", [])

def calculate_dir_checksum(job: Job, algorithm: ChecksumAlgorithm) -> str:
    """Recursively calculate checksum for DIR by concatenating child checksums."""
    print("=== calculate_dir_checksum called ===")
    print(f"DIR fileId: {job.args['file'].get('fileId')}")
    print(f"DIR domain: {job.ctx.get('oneproviderDomain')}")
    print(f"DIR algorithm: {algorithm}")
    children = list_dir_children(job)
    print(f"DIR children count: {len(children)}")
    child_checksums = []
    xattr_name = job.ctx["config"].get("metadataKey")
    for child in children:
        print(f"DIR child fileId: {child.get('fileId')}, type: {child.get('type')}")
        child_job = Job(
            ctx=job.ctx,
            args={"file": child}
        )
        file_type = child.get("type")
        if file_type == "REG":
            print(f"Calculating checksum for REG child {child.get('fileId')}")
            data_stream = get_file_data_stream(child_job)
            checksum = calculate_checksum(algorithm, data_stream)
        elif file_type == "DIR":
            print(f"Recursively calculating checksum for DIR child {child.get('fileId')}")
            checksum = calculate_dir_checksum(child_job, algorithm)
        else:
            print(f"Unknown child type for {child.get('fileId')}")
            checksum = ""
        # Set checksum metadata for every child
        print(f"Child checksum: {checksum}")
        if checksum and xattr_name:
            set_file_xattr(child_job, xattr_name, checksum)
        child_checksums.append(checksum or "")
    # Concatenate all child checksums and hash the result for the DIR checksum
    print(f"All child checksums: {child_checksums}")
    concat = "".join(child_checksums).encode()
    if algorithm == "adler32":
        value = zlib.adler32(concat, 1)
        dir_checksum = format(value, "x")
    else:
        data_hash = getattr(hashlib, algorithm)()
        data_hash.update(concat)
        dir_checksum = data_hash.hexdigest()
    print(f"DIR checksum: {dir_checksum}")
    # Set checksum metadata for the directory itself
    if dir_checksum and xattr_name:
        set_file_xattr(job, xattr_name, dir_checksum)
    return dir_checksum


def build_job_results(job: Job, checksum: Optional[str]) -> JobResults:
    return {
        "result": {
            "fileId": job.args["file"]["fileId"],
            "algorithm": job.ctx["config"]["algorithm"],
            "checksum": checksum,
        }
    }


def get_file_data_stream(job: Job) -> Iterator[bytes]:
    response = requests.get(
        build_file_rest_url(job, "content"),
        headers={"x-auth-token": job.ctx["accessToken"]},
        stream=True,
        verify=VERIFY_SSL_CERTS,
        timeout=EXTENDED_REST_REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    return response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE)


def calculate_checksum(
    algorithm: ChecksumAlgorithm, data_stream: Iterator[bytes]
) -> str:
    if algorithm == "adler32":
        value = 1
        for data in data_stream:
            value = zlib.adler32(data, value)
            _measurements_queue.put(BytesProcessed.build(value=len(data)))
        return format(value, "x")

    data_hash = getattr(hashlib, algorithm)()
    for data in data_stream:
        data_hash.update(data)
        _measurements_queue.put(BytesProcessed.build(value=len(data)))
    return data_hash.hexdigest()


def set_file_xattr(job: Job, xattr_name: str, checksum: str) -> None:
    print("=== set_file_xattr called ===")
    print(f"fileId: {job.args['file'].get('fileId')}")
    print(f"type: {job.args['file'].get('type')}")
    print(f"domain: {job.ctx.get('oneproviderDomain')}")
    print(f"xattr_name: {xattr_name}")
    print(f"checksum: {checksum}")
    url = build_file_rest_url(job, "metadata/xattrs")
    print(f"PUT URL: {url}")
    headers = {
        "x-auth-token": job.ctx["accessToken"],
        "content-type": "application/json",
    }
    print(f"Headers: {headers}")
    payload = {xattr_name: checksum}
    print(f"Payload: {payload}")
    response = requests.put(
        url,
        headers=headers,
        json=payload,
        verify=VERIFY_SSL_CERTS,
        timeout=REST_REQUEST_TIMEOUT,
    )
    print(f"DEBUG Response status: {response.status_code}")
    print(f"DEBUG Response body: {response.text}")
    response.raise_for_status()


def build_file_rest_url(job: Job, subpath: str) -> str:
    domain = job.ctx["oneproviderDomain"]
    file_id = job.args["file"]["fileId"]
    subpath = subpath.lstrip("/")

    print(f"https://{domain}/api/v3/oneprovider/data/{file_id}/{subpath}")
    return f"https://{domain}/api/v3/oneprovider/data/{file_id}/{subpath}"


def monitor_jobs(heartbeat_callback: AtmHeartbeatCallback) -> None:
    any_job_ongoing = True
    while any_job_ongoing:
        any_job_ongoing = not _all_jobs_processed.wait(timeout=1)

        measurements = []
        while not _measurements_queue.empty():
            measurements.append(_measurements_queue.get())

        if measurements:
            STATS_STREAMER.stream_items(measurements)
            heartbeat_callback()