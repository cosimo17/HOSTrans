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
        return buffer.raw
    except Exception:
        return None


def read_int(handle, address):
    data = read_process_memory(handle, address, 4)
    if data is None:
        return None
    return int.from_bytes(data, 'little')


def read_float(handle, address):
    data = read_process_memory(handle, address, 4)
    if data is None:
        return None
    return struct.unpack('<f', data)[0]


def read_string(handle, address, max_length=100, encoding_format='utf-8'):
    """根据编码格式使用不同的读取和终止策略"""
    if encoding_format in ('utf-16le', 'utf-16'):
        # UTF-16: 每次读取2字节，遇到 \x00\x00 终止
        buffer = bytearray()
        for i in range(0, max_length, 2):
            chunk = read_process_memory(handle, address + i, 2)
            if not chunk or chunk == b"\x00\x00":
                break
            buffer.extend(chunk)
    else:
        # UTF-8: 每次读取1字节，遇到 \x00 终止
        buffer = bytearray()
        for i in range(max_length):
            chunk = read_process_memory(handle, address + i, 1)
            if not chunk or chunk == b"\x00":
                break
            buffer.extend(chunk)
    try:
        return buffer.decode(encoding_format)
    except UnicodeDecodeError:
        return buffer.decode(encoding_format, errors="ignore")


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

        # 防止 RegionSize 为 0 导致无限循环
        if mbi.RegionSize == 0:
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
