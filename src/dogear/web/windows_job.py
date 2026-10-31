"""A Windows Job object that ends every process in it when it is closed.

The server puts each child in one, so stopping a child also stops what the child started
(ffmpeg, espeak-ng): Windows has no process groups to signal, and ending a process
doesn't end its children. Closing the job ends anything still in it, and Windows closes
it when the server ends however it ends, so nothing outlives the server either.

Only used on Windows, through ctypes (no extra package). The structures use fixed-size
integers so their layout can be checked on any system.
"""

from __future__ import annotations

import ctypes

JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9  # the JOBOBJECTINFOCLASS value
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
PROCESS_TERMINATE = 0x0001
PROCESS_SET_QUOTA = 0x0100


class IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_uint64)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class BasicLimits(ctypes.Structure):  # JOBOBJECT_BASIC_LIMIT_INFORMATION
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class ExtendedLimits(ctypes.Structure):  # JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    _fields_ = [
        ("BasicLimitInformation", BasicLimits),
        ("IoInfo", IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class Job:
    """A job holding one child and everything it starts."""

    def __init__(self, kernel32, handle: int) -> None:
        self._kernel32 = kernel32
        self._handle: int | None = handle

    @classmethod
    def adopt(cls, pid: int) -> Job:
        """A new job holding the process `pid` and every process it starts from now on.
        (The child is put in the job just after it starts. `dogear` takes far longer
        than that to start anything of its own.)"""
        kernel32 = _kernel32()
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        job = cls(kernel32, handle)
        try:
            limits = ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel32.SetInformationJobObject(
                handle,
                JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                ctypes.byref(limits),
                ctypes.sizeof(limits),
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            process = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
            if not process:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if not kernel32.AssignProcessToJobObject(handle, process):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                kernel32.CloseHandle(process)
        except BaseException:
            job.close()
            raise
        return job

    def terminate(self, exit_code: int) -> None:
        """End every process in the job now."""
        if self._handle is not None and not self._kernel32.TerminateJobObject(
            self._handle, exit_code
        ):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        """Let go of the job, which ends any process still in it."""
        handle, self._handle = self._handle, None
        if handle is not None:
            self._kernel32.CloseHandle(handle)


def _kernel32():
    """kernel32 with the argument and result types of the functions used here. Its own
    instance, so these types don't change kernel32 for other code in the process."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle, dword, boolean = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int
    signatures = {
        "CreateJobObjectW": ((ctypes.c_void_p, ctypes.c_wchar_p), handle),
        "SetInformationJobObject": ((handle, ctypes.c_int, ctypes.c_void_p, dword), boolean),
        "OpenProcess": ((dword, boolean, dword), handle),
        "AssignProcessToJobObject": ((handle, handle), boolean),
        "TerminateJobObject": ((handle, ctypes.c_uint), boolean),
        "CloseHandle": ((handle,), boolean),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(kernel32, name)
        function.argtypes = arguments
        function.restype = result
    return kernel32
