"""Lifetime of owned subprocess trees; never manages an external SC session."""
import os
import signal
import subprocess


class ProcessScope:
    def __init__(self):
        self.process = None
        self.job = None
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes as w
            class Basic(ctypes.Structure):
                _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                    ("flags", w.DWORD), ("min_working", ctypes.c_size_t), ("max_working", ctypes.c_size_t),
                    ("active_processes", w.DWORD), ("affinity", ctypes.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]
            class IO(ctypes.Structure): _fields_ = [(name, ctypes.c_ulonglong) for name in ("read_ops","write_ops","other_ops","read_bytes","write_bytes","other_bytes")]
            class Extended(ctypes.Structure):
                _fields_ = [("basic", Basic), ("io", IO), ("process_memory", ctypes.c_size_t),
                            ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]; self.kernel.CreateJobObjectW.restype = w.HANDLE
            self.kernel.SetInformationJobObject.argtypes = [w.HANDLE,w.INT,ctypes.c_void_p,w.DWORD]
            self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE,w.HANDLE]
            self.kernel.CloseHandle.argtypes = [w.HANDLE]
            self.job = self.kernel.CreateJobObjectW(None, None)
            if not self.job: raise ctypes.WinError(ctypes.get_last_error())
            limits = Extended(); limits.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE
            if not self.kernel.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                self.close(); raise ctypes.WinError(ctypes.get_last_error())

    def launch(self, args, **kwargs):
        if os.name != "nt": kwargs["start_new_session"] = True
        self.process = subprocess.Popen(args, **kwargs)
        if self.job:
            import ctypes
            if not self.kernel.AssignProcessToJobObject(self.job, int(self.process._handle)):
                error = ctypes.get_last_error()
                self.process.terminate(); self.process.wait(timeout=4); self.close()
                raise ctypes.WinError(error)
        return self.process

    def close(self):
        if self.job:
            self.kernel.CloseHandle(self.job); self.job = None
        elif os.name != "nt" and self.process:
            try: os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
