#!/bin/sh
# 저장소 안의 훅 디렉터리를 사용하도록 설정한다(로컬 설정, 되돌리기: git config --unset core.hooksPath).
ROOT="$(git rev-parse --show-toplevel)"
chmod +x "$ROOT/tools/safety/hooks/pre-commit"
git -C "$ROOT" config core.hooksPath tools/safety/hooks
echo "core.hooksPath = tools/safety/hooks"
echo "※ 훅은 --no-verify 로 우회할 수 있다. 푸시 전 'python3 -I tools/safety/check_public_safety.py --tracked' 를 반드시 실행한다."
