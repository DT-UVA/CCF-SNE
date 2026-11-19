#!/bin/sh

# SlopBro
# by throwaway96
# https://github.com/throwaway96/slopbro
# Copyright 2024-2026. Licensed under AGPL v3 or later. No warranties.

set -e

SCRIPT_DIR="${SCRIPT_DIR:-$(dirname -- "${0}")}"
SCRIPT_NAME='SlopBro'

is_root() {
    test "$(id -u)" -eq 0
}

# AppID for toasts/alerts
SRC_APPID='com.webos.service.secondscreen.gateway'

toast() {
    title="${SCRIPT_NAME}"
    escape1="${1//\\/\\\\}"
    escape="${escape1//\"/\\\"}"
    payload="$(printf '{"sourceId":"%s","message":"<h3>%s</h3>%s"}' "${SRC_APPID}" "${title}" "${escape}")"

    if is_root; then
        luna-send -w 1000 -n 1 -a "${SRC_APPID}" 'luna://com.webos.notification/createToast' "${payload}" >/dev/null
    else
        luna-send-pub -w 1000 -n 1 'luna://com.webos.notification/createToast' "${payload}" >/dev/null
    fi
}

toast "SlopBro is starting up..."
toast "Has root: $(is_root && echo 'yes' || echo 'no')"