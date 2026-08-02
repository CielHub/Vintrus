# utils/exceptions.py

class ARSBaseException(Exception):
    """Base exception untuk seluruh error pada sistem ARS-2."""
    pass

class AndroidShellError(ARSBaseException):
    """Dilemparkan ketika eksekusi command shell Android mengembalikan exit code non-zero."""
    def __init__(self, command: str, returncode: int, stderr: str):
        self.command = command
        self.returncode = returncode
        self.stderr = stderr.strip()
        super().__init__(f"Command '{command}' failed [Code: {returncode}] -> {self.stderr}")

class ShellTimeoutError(ARSBaseException):
    """Dilemparkan ketika eksekusi shell melewati batas waktu (timeout)."""
    def __init__(self, command: str, timeout: int):
        self.command = command
        self.timeout = timeout
        super().__init__(f"Command '{command}' timed out after {timeout} seconds. Process killed.")

class PackageNotFoundError(ARSBaseException):
    """Dilemparkan ketika package yang direquest tidak ditemukan di sistem."""
    pass
    
