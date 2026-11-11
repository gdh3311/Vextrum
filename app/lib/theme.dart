import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

const accentDark = Color(0xFF72E1D2);
const accentLight = Color(0xFF126D73);
const gold = Color(0xFFFFCA62);
const good = Color(0xFF34C77B);
const bad = Color(0xFFF0616D);
const even = Color(0xFFE0A93B);

final themeModeProvider = StateProvider<ThemeMode>((ref) => ThemeMode.dark);

ColorScheme _scheme(Brightness b) {
  final dark = b == Brightness.dark;
  final bg = dark ? const Color(0xFF0B1423) : const Color(0xFFF2F5F8);
  final side = dark ? const Color(0xFF0E182A) : const Color(0xFFFDFEFF);
  final card = dark ? const Color(0xFF121F33) : const Color(0xFFFFFFFF);
  final raised = dark ? const Color(0xFF192A41) : const Color(0xFFEDF2F6);
  final raised2 = dark ? const Color(0xFF213650) : const Color(0xFFE1EAF2);
  final line = dark ? const Color(0xFF2B3D57) : const Color(0xFFD6E0EB);
  final text = dark ? const Color(0xFFF0F5FC) : const Color(0xFF15243A);
  final muted = dark ? const Color(0xFFADBED3) : const Color(0xFF506681);
  final accent = dark ? accentDark : accentLight;
  return ColorScheme(
    brightness: b,
    primary: accent,
    onPrimary: dark ? const Color(0xFF04211D) : Colors.white,
    primaryContainer: accent.withOpacity(.16),
    onPrimaryContainer: accent,
    secondary: accent,
    onSecondary: dark ? const Color(0xFF04211D) : Colors.white,
    secondaryContainer: raised2,
    onSecondaryContainer: text,
    tertiary: gold,
    onTertiary: const Color(0xFF2B1D00),
    error: bad,
    onError: Colors.white,
    surface: bg,
    onSurface: text,
    onSurfaceVariant: muted,
    surfaceContainerLowest: side,
    surfaceContainerLow: card,
    surfaceContainer: raised,
    surfaceContainerHigh: raised,
    surfaceContainerHighest: raised2,
    outline: dark ? const Color(0xFF4A5263) : const Color(0xFFB4BBC7),
    outlineVariant: line,
    inverseSurface: text,
    onInverseSurface: bg,
    inversePrimary: accent,
    surfaceTint: Colors.transparent,
  );
}

ThemeData buildTheme(Brightness b) {
  final cs = _scheme(b);
  // Pretendard 에 없는 일본어 글자는 시스템 글꼴로 그린다.
  final base = ThemeData(colorScheme: cs, useMaterial3: true, brightness: b, fontFamily: 'Pretendard',
      fontFamilyFallback: const ['Yu Gothic UI', 'Meiryo', 'Hiragino Sans', 'Noto Sans JP', 'Noto Sans CJK JP', 'Malgun Gothic']);
  const none = BorderSide.none;
  return base.copyWith(
    scaffoldBackgroundColor: cs.surface,
    splashFactory: InkRipple.splashFactory,
    highlightColor: Colors.transparent,
    hoverColor: cs.onSurface.withOpacity(.05),
    textTheme: base.textTheme
        .apply(bodyColor: cs.onSurface, displayColor: cs.onSurface)
        .copyWith(
          headlineSmall: base.textTheme.headlineSmall?.copyWith(fontSize: 24, letterSpacing: -.5, color: cs.onSurface),
          bodyMedium: base.textTheme.bodyMedium?.copyWith(fontSize: 14, height: 1.45, color: cs.onSurface),
          bodySmall: base.textTheme.bodySmall?.copyWith(fontSize: 12.5, height: 1.4, color: cs.onSurfaceVariant),
        ),
    appBarTheme: AppBarTheme(
        backgroundColor: cs.surface, surfaceTintColor: Colors.transparent, elevation: 0, scrolledUnderElevation: 0),
    cardTheme: CardTheme(
        elevation: 0,
        margin: EdgeInsets.zero,
        color: cs.surfaceContainerLow,
        shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(17), side: BorderSide(color: cs.outlineVariant))),
    dialogTheme: DialogTheme(
        backgroundColor: cs.surfaceContainerLow,
        surfaceTintColor: Colors.transparent,
        titleTextStyle: TextStyle(
            fontFamily: 'Pretendard', fontSize: 18, fontWeight: FontWeight.w700, color: cs.onSurface),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16))),
    navigationBarTheme: NavigationBarThemeData(
        backgroundColor: cs.surfaceContainerLowest,
        indicatorColor: cs.primary.withOpacity(.16),
        surfaceTintColor: Colors.transparent,
        height: 64,
        labelTextStyle: const WidgetStatePropertyAll(TextStyle(fontSize: 11, fontWeight: FontWeight.w600))),
    chipTheme: base.chipTheme.copyWith(
        side: BorderSide(color: cs.outlineVariant),
        showCheckmark: false,
        backgroundColor: cs.surfaceContainer,
        selectedColor: cs.primary.withOpacity(.18),
        checkmarkColor: cs.primary,
        labelStyle: TextStyle(fontFamily: 'Pretendard', fontSize: 13, color: cs.onSurface),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8))),
    inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: cs.surfaceContainer,
        hintStyle: TextStyle(color: cs.onSurfaceVariant, fontSize: 14),
        labelStyle: TextStyle(color: cs.onSurfaceVariant),
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: cs.outlineVariant)),
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: cs.outlineVariant)),
        focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10), borderSide: BorderSide(color: cs.primary, width: 1.5))),
    filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            textStyle: const TextStyle(fontFamily: 'Pretendard', fontWeight: FontWeight.w600, fontSize: 14))),
    outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
            foregroundColor: cs.onSurface,
            side: BorderSide(color: cs.outline.withOpacity(.6)),
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            textStyle: const TextStyle(fontFamily: 'Pretendard', fontWeight: FontWeight.w600, fontSize: 13))),
    textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
            foregroundColor: cs.onSurfaceVariant,
            textStyle: const TextStyle(fontFamily: 'Pretendard', fontWeight: FontWeight.w600, fontSize: 13))),
    segmentedButtonTheme: SegmentedButtonThemeData(
        style: ButtonStyle(
            side: const WidgetStatePropertyAll(none),
            shape: WidgetStatePropertyAll(RoundedRectangleBorder(borderRadius: BorderRadius.circular(9))),
            backgroundColor: WidgetStateProperty.resolveWith(
                (s) => s.contains(WidgetState.selected) ? cs.surfaceContainerHighest : cs.surfaceContainer),
            foregroundColor: WidgetStateProperty.resolveWith(
                (s) => s.contains(WidgetState.selected) ? cs.onSurface : cs.onSurfaceVariant),
            textStyle: const WidgetStatePropertyAll(
                TextStyle(fontFamily: 'Pretendard', fontWeight: FontWeight.w600, fontSize: 13)))),
    progressIndicatorTheme: ProgressIndicatorThemeData(color: cs.primary, linearTrackColor: cs.surfaceContainer),
    sliderTheme: base.sliderTheme.copyWith(
        inactiveTrackColor: cs.surfaceContainerHighest, trackHeight: 4, overlayShape: SliderComponentShape.noOverlay),
    dividerTheme: DividerThemeData(color: cs.outlineVariant, thickness: 1, space: 1),
    listTileTheme: ListTileThemeData(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        titleTextStyle: TextStyle(fontFamily: 'Pretendard', fontSize: 14, color: cs.onSurface),
        subtitleTextStyle: TextStyle(fontFamily: 'Pretendard', fontSize: 12.5, color: cs.onSurfaceVariant)),
    tooltipTheme: TooltipThemeData(
        waitDuration: const Duration(milliseconds: 300),
        decoration: BoxDecoration(color: cs.surfaceContainerHighest, borderRadius: BorderRadius.circular(8)),
        textStyle: TextStyle(fontFamily: 'Pretendard', color: cs.onSurface, fontSize: 12.5)),
    snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        insetPadding: const EdgeInsets.fromLTRB(14, 5, 14, 12),
        backgroundColor: cs.surfaceContainerHighest,
        contentTextStyle: TextStyle(fontFamily: 'Pretendard', color: cs.onSurface, fontSize: 14),
        actionTextColor: cs.primary,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10))),
  );
}
