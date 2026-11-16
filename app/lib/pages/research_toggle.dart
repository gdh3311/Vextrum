import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart' hide Text, Tooltip;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api.dart';
import '../i18n.dart';
import '../settings.dart';

final _researchControlProvider = FutureProvider.autoDispose<Json>((ref) async {
  ref.watch(apiContextProvider);
  final Json state;
  try {
    state = (await dio.get('/api/research/control')).data as Json;
  } on DioException catch (error) {
    if (error.response?.statusCode != 405) rethrow;
    return {...(await dio.get('/api/research/status')).data as Json, 'legacy': true};
  }
  if (state['stopping'] == true) {
    final timer = Timer(const Duration(milliseconds: 400), ref.invalidateSelf);
    ref.onDispose(timer.cancel);
  }
  return state;
});

class ResearchToggle extends ConsumerStatefulWidget {
  const ResearchToggle({super.key, this.onChanged});
  final VoidCallback? onChanged;

  @override
  ConsumerState<ResearchToggle> createState() => _ResearchToggleState();
}

class _ResearchToggleState extends ConsumerState<ResearchToggle> {
  bool _sending = false;
  String? _error;

  Future<void> _setRunning(bool running) async {
    final server = ref.read(apiContextProvider);
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      await dio.post('/api/research/control', data: {'running': running});
      if (!mounted || ref.read(apiContextProvider) != server) return;
      ref.invalidate(_researchControlProvider);
      widget.onChanged?.call();
    } on DioException catch (error) {
      if (mounted && ref.read(apiContextProvider) == server) {
        setState(() => _error = error.response?.statusCode == 409
            ? '중지를 마친 뒤 다시 켤 수 있습니다.'
            : '자동 연구 설정을 저장하지 못했습니다.');
        ref.invalidate(_researchControlProvider);
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final status = ref.watch(_researchControlProvider);
    final running = status.valueOrNull?['running'] == true;
    final stopping = status.valueOrNull?['stopping'] == true;
    final legacy = status.valueOrNull?['legacy'] == true;
    final subtitle = _error ?? (status.hasError
        ? '자동 연구 상태를 확인할 수 없습니다.'
        : stopping
            ? '진행 중인 연구를 멈추는 중입니다.'
            : legacy
                ? '이전 버전 서버에 연결되어 있습니다. 중지하면 진행 중인 연구를 마친 뒤 멈춥니다.'
                : '켜 두면 앱을 다시 열 때도 실행합니다. 저장된 연구 결과는 중지 후에도 볼 수 있습니다.');
    return SwitchListTile(
      contentPadding: EdgeInsets.zero,
      title: const Text('백그라운드 자동 연구'),
      subtitle: Text(subtitle),
      value: running,
      secondary: status.hasError
          ? IconButton(
              tooltip: tr('다시 시도'),
              onPressed: () => ref.invalidate(_researchControlProvider),
              icon: const Icon(Icons.refresh),
            )
          : null,
      onChanged: _sending || status.isLoading || status.hasError || stopping ? null : _setRunning,
    );
  }
}
