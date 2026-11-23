SCRIPT_NAME='Forensics tool'
REMOTE_HOST="10.0.0.1"
REMOTE_PORT="4444"
DD_LOG=/tmp/dd_progress.log
FIFO=/tmp/dd_fifo
SRC_APPID='com.webos.service.secondscreen.gateway'

def main():
    toast("Hello from python!")

def toast(message):
    payload = {
        "sourceId": SRC_APPID,
        "message": f"<h3>{SCRIPT_NAME}</h3>{message}"
    }

    subprocess.run(
        [
            "luna-send",
            "-w", "1000",
            "-n", "1",
            "-a", SRC_APPID,
            "luna://com.webos.notification/createToast",
            json.dumps(payload)
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False
    )

if __name__ == "__main__":
    main()