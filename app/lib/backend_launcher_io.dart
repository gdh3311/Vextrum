import 'dart:async';
import 'dart:io';

/// 앱이 직접 켠 백엔드의 프로세스 번호 (이미 켜져 있던 백엔드는 건드리지 않는다).
int? _startedPid;

/// 실행 파일 옆 backend\vextrum-backend.exe 를 찾는다. 개발 빌드처럼 없으면 null.
File? _bundledBackend() {
  if (!Platform.isWindows) return null;
  final dir = File(Platform.resolvedExecutable).parent.path;
  final exe = File('$dir${Platform.pathSeparator}backend${Platform.pathSeparator}vextrum-backend.exe');
  return exe.existsSync() ? exe : null;
}

Future<bool> _alive() async {
  final client = HttpClient()..connectionTimeout = const Duration(milliseconds: 800);
  try {
    final request = await client.getUrl(Uri.parse('http://127.0.0.1:8000/api/info'));
    final response = await request.close().timeout(const Duration(seconds: 2));
    await response.drain<void>();
    return response.statusCode == 200;
  } catch (_) {
    return false;
  } finally {
    client.close(force: true);
  }
}

/// 배포판이면 백엔드가 응답할 때까지(최대 20초) 켜 둔다. 이미 켜져 있으면 그대로 쓴다.
Future<void> ensureLocalBackend() async {
  final exe = _bundledBackend();
  if (exe == null || await _alive()) return;
  try {
    final process = await Process.start(exe.path, const [],
        workingDirectory: exe.parent.path, mode: ProcessStartMode.detached);
    _startedPid = process.pid;
  } catch (_) {
    return; // 못 켜면 앱 화면에서 '서버에 연결할 수 없음' 안내가 나온다
  }
  final deadline = DateTime.now().add(const Duration(seconds: 20));
  while (DateTime.now().isBefore(deadline)) {
    if (await _alive()) return;
    await Future<void>.delayed(const Duration(milliseconds: 300));
  }
}

/// 앱이 켠 백엔드만 끈다 (/T: 시뮬레이션 작업 프로세스까지).
void stopLocalBackend() {
  final pid = _startedPid;
  if (pid == null) return;
  _startedPid = null;
  try {
    Process.runSync('taskkill', ['/PID', '$pid', '/T', '/F']);
  } catch (_) {}
}
