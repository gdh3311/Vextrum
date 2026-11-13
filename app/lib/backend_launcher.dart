// 배포판(압축 파일)에서 백엔드를 앱이 직접 켜고 끈다.
// 웹에는 프로세스가 없으므로 빈 구현을 쓴다.
export 'backend_launcher_stub.dart' if (dart.library.io) 'backend_launcher_io.dart';
