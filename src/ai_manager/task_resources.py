"""Best-effort observation of this owned image worker, never an OS hard quota."""
import os


def sample(owner):
    if os.name!='nt':raise ValueError('resource_guard_unavailable')
    import ctypes
    from ctypes import wintypes
    class Memory(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
    class System(ctypes.Structure):
        _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD)]+[(name,ctypes.c_ulonglong) for name in ('total_physical','available_physical','total_pagefile','available_pagefile','total_virtual','available_virtual','available_extended_virtual')]
    class Members(ctypes.Structure):
        _fields_=[('assigned',wintypes.DWORD),('count',wintypes.DWORD),('pids',ctypes.c_size_t*64)]
    system=System();system.length=ctypes.sizeof(system)
    psapi=ctypes.WinDLL('psapi',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Memory),wintypes.DWORD]
    kernel.GlobalMemoryStatusEx.argtypes=[ctypes.POINTER(System)]
    kernel.QueryInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p]
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    members=Members()
    if not getattr(owner,'job',None) or not kernel.QueryInformationJobObject(owner.job,3,ctypes.byref(members),ctypes.sizeof(members),None) or members.count>64 or members.count!=members.assigned:raise ValueError('resource_guard_unavailable')
    resident=peak=observed=0
    for pid in members.pids[:members.count]:
        # Enumerate only members of this exact owned Job; never scan the system.
        handle=kernel.OpenProcess(0x410,False,pid)
        if not handle:
            if ctypes.get_last_error()==87:continue  # PID exited after enumeration.
            raise ValueError('resource_guard_unavailable')
        try:
            info=Memory();info.cb=ctypes.sizeof(info)
            if not psapi.GetProcessMemoryInfo(handle,ctypes.byref(info),info.cb):
                exit_code=wintypes.DWORD()
                if kernel.GetExitCodeProcess(handle,ctypes.byref(exit_code)) and exit_code.value!=259:continue
                raise ValueError('resource_guard_unavailable')
            resident+=info.WorkingSetSize;peak+=info.PeakWorkingSetSize;observed+=1
        finally:kernel.CloseHandle(handle)
    if not observed or not kernel.GlobalMemoryStatusEx(ctypes.byref(system)):raise ValueError('resource_guard_unavailable')
    return dict(rss_bytes=resident,peak_rss_bytes=peak,available_physical_bytes=system.available_physical,process_count=observed,scope='owned_job_processes')


def enforce(value,max_rss_gib=18):
    if value['rss_bytes']>max_rss_gib*1024**3 or value['available_physical_bytes']<3*1024**3:raise ValueError('resource_limit_reached')
