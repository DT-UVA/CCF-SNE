#!/bin/sh

SCRIPT_NAME='ddTV'
REMOTE_HOST="10.0.0.1"
REMOTE_PORT="4444"
DD_LOG=/tmp/dd_progress.log
FIFO=/tmp/dd_fifo
SRC_APPID='com.webos.service.secondscreen.gateway'

toast() {
    escape1="${1//\\/\\\\}"
    escape="${escape1//\"/\\\"}"
    payload="$(printf '{"sourceId":"%s","message":"<h3>%s</h3>%s"}' "${SRC_APPID}" "${SCRIPT_NAME}" "${escape}")"
    luna-send -w 1000 -n 1 -a "${SRC_APPID}" 'luna://com.webos.notification/createToast' "${payload}" >/dev/null
}

toast "Starting script"
python3 payload.py
toast "Script finished"


# toast "Exporting disk to ${REMOTE_HOST}:${REMOTE_PORT}..."

# # Named pipe so we can get dd's PID separately
# mkfifo "${FIFO}"

# # dd writes to fifo — we now have its actual PID
# dd if=/dev/mmcblk0 bs=4M 2>"${DD_LOG}" > "${FIFO}" &
# DD_PID=$!

# # nc reads from fifo
# nc "${REMOTE_HOST}" "${REMOTE_PORT}" < "${FIFO}" &

# # Signal dd every 10 seconds and toast its output
# while kill -USR1 "${DD_PID}" 2>/dev/null; do
#     sleep 10
#     MSG=$(tail -1 "${DD_LOG}")
#     [ -n "${MSG}" ] && toast "${MSG}"
# done

# wait "${DD_PID}"
# rm -f "${FIFO}"
# toast "Disk export complete."