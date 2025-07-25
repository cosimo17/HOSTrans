import ctypes
from ctypes import wintypes
import psutil
import struct

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
PAGE_READWRITE = 0x04

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE

kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    wintypes.LPCVOID,
    wintypes.LPVOID,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t)
]
kernel32.ReadProcessMemory.restype = wintypes.BOOL

kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
CloseHandle = kernel32.CloseHandle

# 正确定义 MEMORY_BASIC_INFORMATION 结构体
class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD)
    ]


# 修正 VirtualQueryEx 定义
VirtualQueryEx = kernel32.VirtualQueryEx
VirtualQueryEx.argtypes = [wintypes.HANDLE, wintypes.LPCVOID, ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t]
VirtualQueryEx.restype = ctypes.c_size_t


def get_process_id(process_name):
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] == process_name:
            return proc.info['pid']
    raise Exception("Process not found")


def get_process_handle(pid):
    handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle

def read_process_memory(process_handle, address, size=4):
    # process_handle = kernel32.OpenProcess(
    #     PROCESS_VM_READ | PROCESS_QUERY_INFORMATION,
    #     False,
    #     pid
    # )
    # if not process_handle:
    #     raise ctypes.WinError(ctypes.get_last_error())

    try:
        buffer = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t()
        if not kernel32.ReadProcessMemory(
                process_handle,
                address,
                buffer,
                size,
                ctypes.byref(bytes_read)
        ):
            return None
            # raise ctypes.WinError(ctypes.get_last_error())
        return buffer.raw
    except:
        return None
    # finally:
    #     kernel32.CloseHandle(process_handle)


def read_int(pid, address):
    data = read_process_memory(pid, address, 4)
    return int.from_bytes(data, 'little')


def read_float(pid, address):
    data = read_process_memory(pid, address, 4)
    return struct.unpack('<f', data)[0]


def read_string(pid, address, max_length=100, encoding_format='utf-8'):
    data = read_process_memory(pid, address, max_length)
    if data is None:
        return data
    return data.split(b'\x00')[0].decode(encoding=encoding_format)


def scan_memory_bytes(handle, pattern_bytes):
    """搜索字节序列"""
    mbi = MEMORY_BASIC_INFORMATION()
    address = 0
    found_addresses = []
    pattern_len = len(pattern_bytes)

    while True:
        # 查询内存区域信息
        if not VirtualQueryEx(handle, address, ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break

        if mbi.Protect & PAGE_READWRITE and mbi.State == 0x1000:  # MEM_COMMIT
            try:
                # 读取内存区域
                buffer = (ctypes.c_byte * mbi.RegionSize)()
                bytes_read = ctypes.c_size_t()

                if kernel32.ReadProcessMemory(handle, mbi.BaseAddress, buffer, mbi.RegionSize, ctypes.byref(bytes_read)):
                    # 转换为bytes进行搜索
                    region_data = bytes(buffer)

                    # 搜索所有匹配位置
                    pos = 0
                    while pos < len(region_data):
                        match_pos = region_data.find(pattern_bytes, pos)
                        if match_pos == -1:
                            break
                        found_address = mbi.BaseAddress + match_pos
                        found_addresses.append(found_address)
                        pos = match_pos + 1
            except Exception as e:
                print(f"读取内存区域 {hex(address)} 时出错: {e}")

        address += mbi.RegionSize
        if address == 0:  # 防止无限循环
            break

    return found_addresses

