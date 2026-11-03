import win32pipe

APP_NAME                = "NEXO App"
APP_DATA_FOLDER_NAME    = "nexoapp"
APP_DEBUG               = True

CLOUDFLARE_SERVICE_NAME = "cloudflare_tunnel"
CLOUDFLARE_SERVICE_URLS = {
    "amd64":   "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
    "x86_64":  "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
    "x86":     "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-386.exe",
    "i386":    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-386.exe",
    "i686":    "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-386.exe",
    "arm64":   "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-arm64.exe",
    "aarch64": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-arm64.exe",
}

APP_PIPE_DEBUG_ENABLED:        bool       = True
APP_PIPE_NAME:                 str        = r"\\.\pipe\\" + APP_NAME.replace(" ", "").upper()
APP_PIPE_CONNECTION_TYPE:      int        = win32pipe.PIPE_ACCESS_DUPLEX
APP_PIPE_TYPE:                 int        = win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE
APP_PIPE_WAIT:                 int        = win32pipe.PIPE_WAIT
APP_PIPE_ALLOWED_CLIENT:       int        = win32pipe.PIPE_UNLIMITED_INSTANCES
APP_PIPE_BUFFER_SIZE:          int        = 65536
APP_PIPE_MAX_BYTE_READ:        int        = 4096
APP_PIPE_IN_BUFFER_SIZE:       int        = APP_PIPE_BUFFER_SIZE
APP_PIPE_OUT_BUFFER_SIZE:      int        = APP_PIPE_BUFFER_SIZE
APP_PIPE_ERROR_SEM_TIMEOUT:    int        = 121
APP_PIPE_ERROR_PIPE_CONNECTED: int        = 535
APP_PIPE_ERROR_MORE_DATA:      int        = 234
APP_PIPE_IDLE_CHECK_INTERVAL:  int        = 1 #5, should return to 5 in production
APP_PIPE_IDLE_MAX_RETRIES:     int        = 1 #5, should return to 5 in production
APP_PIPE_POLL_INTERVAL:        float      = 0.01
APP_PIPE_SERVER_JOB:           str        = "SERVER"
APP_PIPE_ALL_JOBS:             str        = "*"
APP_PIPE_BROKEN_CODES:         tuple[int] = (109, 233, 232, 6)