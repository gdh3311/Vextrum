"""배포판 백엔드 진입점 (PyInstaller로 vextrum-backend.exe 가 된다).

시뮬레이션은 프로세스 풀을 쓰므로, 얼린(frozen) 실행 파일에서는 freeze_support 가 먼저 돌아야
자식 프로세스가 서버를 또 띄우지 않는다.
"""
import multiprocessing
import os
import sys


def main():
    import uvicorn

    from app.main import app

    port = int(os.environ.get("VEXTRUM_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", log_config=None)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    # --noconsole 빌드에서는 표준 출력이 없다 → 로그를 쓰는 라이브러리가 넘어지지 않게 빈 스트림을 단다.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    main()
